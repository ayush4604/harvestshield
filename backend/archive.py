"""Keyless CEDA public-report archive adapter for noncommercial research.

Keep raw responses and exclusion counts. Monthly windows prevent the public
download's observed 1,000-row cap from silently truncating multiyear history.
"""
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import time

import numpy as np
import pandas as pd
import requests

from .config import today_ist
from .data import CSV_COLUMNS, IDENTITY, PRICES, ProjectError, Store, UNIT, normalize_frame

BASE = "https://agmarknet.ceda.ashoka.edu.in/api"
LOGO_URL = "https://viz.ceda.ashoka.edu.in/assets/logo.png"
PILOT_MARKETS = ["Pune", "Pune(Khadiki)", "Pune(Moshi)", "Pune(Pimpri)"]
SOURCE = "CEDA Agri Market Data / AGMARKNET-DMI public reports; https://agmarknet.ceda.ashoka.edu.in/; INR/quintal; grade unreported"
_last_request = 0.0


def _request(path, payload=None):
    global _last_request
    try:
        for attempt in range(3):
            # Respect the public service rather than parallelizing archive calls.
            pause = max(0.0, 15 - (time.monotonic() - _last_request))
            if pause:
                time.sleep(pause)
            _last_request = time.monotonic()
            if payload is None:
                response = requests.get(BASE + path, timeout=(5, 25))
            else:
                response = requests.post(BASE + path, json=payload, timeout=(5, 35))
            if response.status_code != 429:
                break
            delay = response.headers.get("Retry-After", "30")
            try:
                delay = float(delay)
            except ValueError:
                delay = 30
            if delay > 120:
                raise ProjectError(f"Archive rate limit asks for {delay:.0f} seconds before retry. Cached windows are preserved; retry later.", 429)
            for _ in range(max(1, int(np.ceil(max(delay, 1) / 30)))):
                time.sleep(min(30, max(delay, 1)))
        if response.status_code != 200:
            raise ProjectError(f"CEDA public reports returned HTTP {response.status_code}.", 502)
        if len(response.content) > 20 * 1024 * 1024:
            raise ProjectError("Archive response exceeded 20 MB.", 502)
        data = response.json().get("data")
        if not isinstance(data, list):
            raise ProjectError("CEDA report schema changed.", 502)
        return data
    except ProjectError:
        raise
    except (requests.RequestException, ValueError, AttributeError):
        raise ProjectError("CEDA public archive unavailable or returned invalid JSON.", 502) from None


def lookup(name, rows, label_field, id_field):
    matching = [r for r in rows if str(r.get(label_field, "")).casefold() == name.strip().casefold()]
    if len(matching) != 1:
        raise ProjectError(f"Unknown or ambiguous archive name: {name}. Use exact CEDA spelling.")
    return int(matching[0][id_field])


def monthly_windows(start, end):
    cursor = start
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(end, next_month - timedelta(days=1))
        yield cursor, stop
        cursor = stop + timedelta(days=1)


def normalize_archive(records, state, district, commodity, markets, variety):
    if not records:
        raise ProjectError("No archive records in this date range.", 404)
    raw = pd.DataFrame(records)
    mapping = {"t": "date", "cmdty": "commodity", "market_name": "market", "state_name": "state",
               "district_name": "district", "p_min": "min_price", "p_max": "max_price", "p_modal": "modal_price"}
    needed = set(mapping) | {"variety"}
    if not needed.issubset(raw.columns):
        raise ProjectError("Archive missing identity/price fields; do not fabricate them.", 502)
    frame = raw.rename(columns=mapping).copy()
    selected = frame.state.eq(state) & frame.district.eq(district) & frame.commodity.eq(commodity)
    selected &= frame.market.isin(markets) & frame.variety.eq(variety)
    frame = frame[selected].copy()
    if frame.empty:
        raise ProjectError("No records for the selected markets and exact variety.", 404)
    selected_count = len(frame)
    frame["unit"] = UNIT  # Source page labels price as INR/quintal.
    frame["grade"] = "Unspecified"  # Grade is not in this source response.
    for p in PRICES:
        frame[p] = pd.to_numeric(frame[p], errors="coerce")
    parsed = pd.to_datetime(frame.date, format="%Y-%m-%d", errors="coerce")
    valid = parsed.notna() & parsed.dt.date.le(today_ist())
    valid &= np.isfinite(frame[PRICES]).all(axis=1) & frame[PRICES].gt(0).all(axis=1)
    valid &= frame.min_price.le(frame.modal_price) & frame.modal_price.le(frame.max_price)
    bad_count = int((~valid).sum())
    frame = frame[valid][CSV_COLUMNS].drop_duplicates()
    # Reject ambiguous source days from training rather than choose a favorable price.
    ambiguous = frame.duplicated([*IDENTITY, "date"], keep=False)
    ambiguous_count = int(ambiguous.sum())
    frame = frame[~ambiguous].copy()
    return normalize_frame(frame), {"downloaded": len(raw), "selected": selected_count,
        "invalid_excluded": bad_count, "conflicting_rows_excluded": ambiguous_count,
        "usable": len(frame), "grade": "Unspecified", "variety": variety}


def import_archive(store: Store, start: date, end: date, state="Maharashtra", district="Pune",
                   commodity="Tomato", markets=None, variety="Local"):
    if start > end or end > today_ist() or (end - start).days > 4 * 366:
        raise ProjectError("Archive range must be in the past, ordered, and at most four years.")
    markets = markets or PILOT_MARKETS
    if not 1 <= len(markets) <= 20:
        raise ProjectError("Select 1–20 market names.")
    state_id = lookup(state, _request("/states"), "census_state_name", "census_state_id")
    commodity_id = lookup(commodity, _request("/commodities"), "commodity_disp_name", "commodity_id")
    district_id = lookup(district, _request(f"/districts?state_id={state_id}"), "census_district_name", "census_district_id")
    parameters = {"state_id": state_id, "district_id": district_id, "commodity_id": commodity_id,
                  "calculation_type": "d", "chart_type": "datadownload"}
    root = store.settings.data_dir / "raw" / "ceda"
    cache = root / "windows"
    cache.mkdir(parents=True, exist_ok=True)
    all_records, requests_log = [], []
    def fetch_window(begin, stop):
        payload = {**parameters, "start_date": str(begin), "end_date": str(stop)}
        token = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        cache_file = cache / f"{token}.json"
        cached = cache_file.exists()
        if cached:
            records = json.loads(cache_file.read_text(encoding="utf-8"))
        else:
            records = _request("/prices", payload)
            cache_file.write_text(json.dumps(records), encoding="utf-8")
        requests_log.append({"start": str(begin), "end": str(stop), "rows": len(records), "cached": cached})
        print(f"Archive {begin} to {stop}: {len(records)} source rows" + (" (cached)" if cached else ""), flush=True)
        if len(records) >= 1000:
            if begin == stop:
                raise ProjectError("Single-day report hit the 1,000-row limit. Narrow district/commodity; completeness is unverified.")
            middle = begin + (stop - begin) // 2
            return fetch_window(begin, middle) + fetch_window(middle + timedelta(days=1), stop)
        return records
    for begin, stop in monthly_windows(start, end):
        all_records.extend(fetch_window(begin, stop))
    content = json.dumps(all_records, ensure_ascii=False).encode("utf-8")
    digest = sha256(content).hexdigest()
    raw_path = root / f"{digest}.json"
    raw_path.write_bytes(content)
    frame, quality = normalize_archive(all_records, state, district, commodity, markets, variety)
    csv_path = store.settings.data_dir / "imports" / f"ceda_{digest}.csv"
    frame.to_csv(csv_path, index=False)
    note = f"{SOURCE}; downloaded {today_ist()}"
    result = store.ingest(frame, "real", note, csv_path.name)
    manifest = {"source": SOURCE, "source_url": BASE + "/prices", "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "requested_start": str(start), "requested_end": str(end), "state": state, "district": district,
        "commodity": commodity, "markets": markets, "variety": variety, "quality": quality,
        "sha256": digest, "request_windows": requests_log, "raw_file": str(raw_path), "normalized_csv": str(csv_path),
        "actual_first_date": frame.date.min(), "actual_last_date": frame.date.max(),
        "citation": '"CEDA Agri Market Data (CEDA-AMD), 2000-2023". Centre for Economic Data & Analysis, Ashoka University.',
        "terms": "https://ceda.ashoka.edu.in/api-terms-conditions/", "use": "Noncommercial internship research; no CEDA endorsement.",
        "limitations": "Source grade unreported. Local is a broad reported variety category. Archive observations are not current auction quotes."}
    (root / f"{digest}_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "latest_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Attribution asset from the source's terms page. Fail gracefully if unavailable.
    assets = store.settings.data_dir.parent / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    logo = assets / "ceda-logo.png"
    if not logo.exists():
        try:
            response = requests.get(LOGO_URL, timeout=(5, 15))
            if response.status_code == 200 and response.content.startswith(b"\x89PNG") and len(response.content) < 2_000_000:
                logo.write_bytes(response.content)
        except requests.RequestException:
            pass
    result.update({"quality": quality, "first_date": frame.date.min(), "last_date": frame.date.max(),
        "manifest": str(root / f"{digest}_manifest.json"), "note": "Historical observations; freshness gates still apply. Grade is unreported. CEDA/DMI attribution required."})
    return result

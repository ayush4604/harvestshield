"""Bounded, credential-safe connector for the official daily mandi feed."""
import os
import pandas as pd
import requests

from .data import ProjectError, Store, UNIT

ENDPOINT = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"


def refresh_feed(store: Store, state: str, commodity: str, market: str = "", max_pages: int = 3):
    key = os.getenv("DATA_GOV_API_KEY", "").strip()
    if not key:
        raise ProjectError("DATA_GOV_API_KEY is not set in the backend environment. Historical CSV import works without a key.", 409)
    records = []
    for page in range(max_pages):
        params = {"api-key": key, "format": "json", "limit": 1000, "offset": page * 1000,
                  "filters[state]": state, "filters[commodity]": commodity}
        if market:
            params["filters[market]"] = market
        try:
            with requests.get(ENDPOINT, params=params,
                              headers={"User-Agent": "HarvestShield/1.0", "Accept": "application/json"},
                              timeout=(5, 15), stream=True) as response:
                if response.status_code != 200:
                    raise ProjectError(f"Government feed returned HTTP {response.status_code}. Check your key and the resource's current API documentation.", 502)
                chunks, size = [], 0
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > 5 * 1024 * 1024:
                        raise ProjectError("Feed response exceeded the safety size limit.", 502)
                    chunks.append(chunk)
                import json
                payload = json.loads(b"".join(chunks))
        except ProjectError:
            raise
        except requests.Timeout:
            raise ProjectError("Government feed timed out. No data imported; try again later or narrow the market filter.", 502) from None
        except requests.RequestException:
            # Exception text can contain a credential-bearing request URL.
            raise ProjectError("Government feed connection failed. No data imported; check network availability.", 502) from None
        except ValueError:
            raise ProjectError("Government feed returned invalid JSON. No data imported; the provider may be unavailable.", 502) from None
        batch = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(batch, list):
            raise ProjectError("Feed schema changed or API key was rejected. No records imported; check official API documentation.", 502)
        if not batch:
            break
        records.extend(batch)
        if len(batch) < 1000:
            break
    if not records:
        raise ProjectError("No feed records matched these filters. Check official market and crop spellings.", 404)
    frame = pd.DataFrame(records)
    frame.columns = [str(c).lower().strip() for c in frame.columns]
    # This adapter's price contract is the AGMARKNET INR/quintal feed.
    if "unit" not in frame:
        frame["unit"] = UNIT
    # Defend against ignored/upstream-changed filter parameters.
    if not {"state", "commodity", "market"}.issubset(frame.columns):
        raise ProjectError("Government feed is missing market identity fields.", 502)
    mask = frame.state.astype(str).str.strip().str.casefold().eq(state.strip().casefold())
    mask &= frame.commodity.astype(str).str.strip().str.casefold().eq(commodity.strip().casefold())
    if market:
        mask &= frame.market.astype(str).str.strip().str.casefold().eq(market.strip().casefold())
    frame = frame[mask]
    if frame.empty:
        raise ProjectError("Returned feed records did not match requested state/crop/market. Nothing imported.", 404)
    result = store.ingest(frame, "real", "AGMARKNET via data.gov.in daily feed (INR/quintal)")
    result["note"] = "Daily reported snapshot, not auction streaming or historical backfill. Request is bounded; use CSV history for training. Confirm current source units/schema before field use."
    result["page_limit_reached"] = len(records) >= max_pages * 1000
    return result

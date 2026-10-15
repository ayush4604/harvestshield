"""Validated observations, SQLite storage, coverage audit, and labeled demo data."""
from contextlib import contextmanager
from datetime import timedelta, datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import re
import sqlite3

import numpy as np
import pandas as pd

from .config import Settings, today_ist

IDENTITY = ["state", "district", "market", "commodity", "variety", "grade", "unit"]
PRICES = ["min_price", "max_price", "modal_price"]
CSV_COLUMNS = ["date", *IDENTITY, *PRICES]
UNIT = "INR/quintal"
MAX_ROWS = 200_000


class ProjectError(ValueError):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_") for c in frame.columns]
    frame = frame.rename(columns={"arrival_date": "date", "minprice": "min_price", "maxprice": "max_price", "modalprice": "modal_price"})
    if frame.columns.duplicated().any():
        raise ProjectError("Duplicate column names after normalization.")
    if len(frame) == 0 or len(frame) > MAX_ROWS:
        raise ProjectError(f"Supply between 1 and {MAX_ROWS:,} rows.")
    for optional in ("district", "grade"):
        if optional not in frame:
            frame[optional] = "Unspecified"
    missing = sorted(set(CSV_COLUMNS) - set(frame.columns))
    if missing:
        raise ProjectError("Missing columns: " + ", ".join(missing) + ". Download the CSV template.")
    frame = frame[CSV_COLUMNS].copy()
    for col in IDENTITY:
        frame[col] = frame[col].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        if frame[col].isna().any() or frame[col].eq("").any():
            raise ProjectError(f"'{col}' must be specified on every row.")
        if frame[col].str.len().gt(150).any():
            raise ProjectError(f"'{col}' values must be 150 characters or shorter.")
    if not frame["unit"].eq(UNIT).all():
        raise ProjectError("Only INR/quintal is supported. Convert and verify source units before importing.")
    text_dates = frame["date"].astype(str).str.strip()
    parsed = pd.to_datetime(text_dates, format="%Y-%m-%d", errors="coerce")
    other = pd.to_datetime(text_dates, format="%d/%m/%Y", errors="coerce")
    parsed = parsed.fillna(other)
    if parsed.isna().any():
        raise ProjectError("Dates must be YYYY-MM-DD or DD/MM/YYYY; at least one date is invalid.")
    if parsed.dt.date.gt(today_ist()).any():
        raise ProjectError("Observed prices cannot have future dates.")
    frame["date"] = parsed.dt.strftime("%Y-%m-%d")
    for col in PRICES:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype(float)
        if not np.isfinite(frame[col]).all() or frame[col].le(0).any():
            raise ProjectError(f"'{col}' must contain finite positive numbers, never missing values or zero.")
    if ((frame.min_price > frame.modal_price) | (frame.modal_price > frame.max_price)).any():
        raise ProjectError("Each row must satisfy min_price <= modal_price <= max_price.")
    keys = [*IDENTITY, "date"]
    unique = frame.drop_duplicates()
    if unique.duplicated(keys, keep=False).any():
        raise ProjectError("Conflicting prices exist for the same market/crop/variety/grade/date.")
    return unique.sort_values(keys).reset_index(drop=True)


def series_key(row) -> str:
    values = [str(row[c]).casefold() for c in IDENTITY]
    return sha256(json.dumps(values, ensure_ascii=True).encode()).hexdigest()[:20]


def parse_csv(content: bytes) -> pd.DataFrame:
    if len(content) > 20 * 1024 * 1024:
        raise ProjectError("CSV upload exceeds the 20 MB limit.")
    try:
        return normalize_frame(pd.read_csv(BytesIO(content), encoding="utf-8-sig"))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise ProjectError("Could not read a UTF-8 CSV. Check encoding and delimiters.") from exc


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.prepare()
        self.path = settings.data_dir / "harvestshield.sqlite"
        with self.connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS observations (
                mode TEXT NOT NULL CHECK(mode IN ('demo','real')),
                series_id TEXT NOT NULL, date TEXT NOT NULL,
                state TEXT, district TEXT, market TEXT, commodity TEXT,
                variety TEXT, grade TEXT, unit TEXT,
                min_price REAL, max_price REAL, modal_price REAL,
                source TEXT, ingested_at TEXT,
                PRIMARY KEY(mode, series_id, date)
            );
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY, mode TEXT, source TEXT, filename TEXT,
                inserted INTEGER, repeated INTEGER, ingested_at TEXT
            );
            """)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def ingest(self, frame: pd.DataFrame, mode: str, source: str, filename=""):
        if mode not in ("demo", "real"):
            raise ProjectError("Unknown dataset mode.")
        if not source.strip() or len(source) > 500:
            raise ProjectError("Provide a source/provenance note of 1–500 characters.")
        frame = normalize_frame(frame)
        now = datetime.now(timezone.utc).isoformat()
        inserted = repeated = 0
        with self.connection() as conn:
            for row in frame.to_dict("records"):
                sid = series_key(row)
                old = conn.execute("SELECT * FROM observations WHERE mode=? AND series_id=? AND date=?", (mode, sid, row["date"])).fetchone()
                if old:
                    if any(abs(old[p] - row[p]) > 1e-8 for p in PRICES):
                        raise ProjectError(f"Import cancelled: conflicting existing price for {row['market']} on {row['date']}. No rows from this import were committed.", 409)
                    repeated += 1
                    continue
                cols = ["mode", "series_id", *CSV_COLUMNS, "source", "ingested_at"]
                vals = [mode, sid, *[row[c] for c in CSV_COLUMNS], source.strip(), now]
                conn.execute(f"INSERT INTO observations ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", vals)
                inserted += 1
            conn.execute("INSERT INTO imports(mode,source,filename,inserted,repeated,ingested_at) VALUES (?,?,?,?,?,?)", (mode, source, filename, inserted, repeated, now))
        return {"mode": mode, "inserted": inserted, "repeated": repeated, "received": len(frame), "source": source}

    def frame(self, mode: str):
        if mode not in ("demo", "real"):
            raise ProjectError("Unknown dataset mode.")
        with self.connection() as conn:
            return pd.read_sql_query("SELECT * FROM observations WHERE mode=? ORDER BY series_id,date", conn, params=(mode,))

    def audit(self, mode: str):
        frame = self.frame(mode)
        series = []
        for sid, group in frame.groupby("series_id"):
            dates = pd.to_datetime(group.date)
            count = len(group)
            span = int((dates.max() - dates.min()).days + 1)
            future_dates = set(dates)
            labels = sum(d + pd.Timedelta(days=7) in future_dates for d in dates)
            last = group.iloc[-1]
            series.append({
                "series_id": sid, **{c: str(last[c]) for c in IDENTITY},
                "first_date": dates.min().strftime("%Y-%m-%d"),
                "last_date": dates.max().strftime("%Y-%m-%d"), "rows": count,
                "calendar_gap_days": span - count, "coverage_fraction": round(count / span, 3),
                "seven_day_label_count": labels,
                "age_days": (today_ist() - dates.max().date()).days,
                "latest_modal_price": float(last.modal_price), "source": str(last.source),
            })
        return {"mode": mode, "synthetic": mode == "demo", "rows": len(frame), "series": series,
                "note": "Calendar gaps can include market closures; coverage is not a business-day completeness measure."}


def demo_frame(days=1095, seed=42, end_date=None):
    """Fictional data for exercising code, never an estimate of Indian market behavior."""
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end_date or today_ist())
    dates = pd.date_range(end=end, periods=days)
    records = []
    for m, name in enumerate(("Demo Valley Mandi", "Demo Riverside Mandi", "Demo Hill Mandi", "Demo Central Mandi")):
        level, shock = 1800 + m * 130, 0.0
        for i, date in enumerate(dates):
            seasonal = 360 * np.sin(2 * np.pi * i / 365) + 120 * np.cos(2 * np.pi * i / 41)
            # Scheduled fictional stress episodes create some labeled decline events.
            if (i + 11 * m) % 77 == 15:
                shock = -620.0
            else:
                shock *= 0.86
            level = 0.91 * level + 0.09 * (1800 + m * 130 + seasonal + shock) + rng.normal(0, 42)
            price = round(max(350, level + shock * 0.35), 2)
            records.append({"date": date.strftime("%Y-%m-%d"), "state": "Demo State",
                "district": "Fictional District", "market": name, "commodity": "Tomato",
                "variety": "Demo Standard", "grade": "Demo Grade", "unit": UNIT,
                "min_price": round(price * 0.9, 2), "max_price": round(price * 1.12, 2), "modal_price": price})
    return pd.DataFrame(records)

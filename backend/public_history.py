"""Normalize a licensed published history without inventing missing observations."""
from datetime import date, datetime, timezone
import json

import numpy as np
import pandas as pd

from .archive import PILOT_MARKETS
from .data import CSV_COLUMNS, IDENTITY, PRICES, ProjectError, Store, UNIT, normalize_frame

PAGE = "https://www.kaggle.com/datasets/vandeetshah/india-commodity-wise-mandi-dataset"
SOURCE = "Vandeet Shah / Kaggle India Commodity Wise Mandi Dataset v1; historical public release; Apache-2.0; INR/quintal; grade unreported"
MAPPING = {"State Name": "state", "District Name": "district", "Market Name": "market", "Variety": "variety",
           "Reported Date": "date", "Min Price (Rs./Quintal)": "min_price",
           "Max Price (Rs./Quintal)": "max_price", "Modal Price (Rs./Quintal)": "modal_price"}


def normalize_public_subset(source, start=date(2021, 1, 1), end=date(2024, 2, 1)):
    missing = set(MAPPING) - set(source.columns)
    if missing:
        raise ProjectError("Published history schema changed: " + ", ".join(sorted(missing)))
    frame = source.rename(columns=MAPPING).copy()
    parsed = pd.to_datetime(frame.date, format="%d %b %Y", errors="coerce")
    selected = frame.state.eq("Maharashtra") & frame.district.eq("Pune") & frame.market.isin(PILOT_MARKETS)
    selected &= frame.variety.eq("Local") & parsed.dt.date.ge(start) & parsed.dt.date.le(end)
    frame = frame[selected].copy()
    if frame.empty:
        raise ProjectError("No usable pilot-market records in the selected period.")
    frame["date"] = parsed[selected].dt.strftime("%Y-%m-%d")
    frame["commodity"] = "Tomato"  # Downloaded file identity: Tomato.csv.
    frame["grade"] = "Unspecified"
    frame["unit"] = UNIT
    for p in PRICES:
        frame[p] = pd.to_numeric(frame[p], errors="coerce")
    valid = np.isfinite(frame[PRICES]).all(axis=1) & frame[PRICES].gt(0).all(axis=1)
    valid &= frame.min_price.le(frame.modal_price) & frame.modal_price.le(frame.max_price)
    invalid = int((~valid).sum())
    accepted = frame[valid][CSV_COLUMNS]
    repeats = len(accepted) - len(accepted.drop_duplicates())
    accepted = accepted.drop_duplicates()
    conflicting = accepted.duplicated([*IDENTITY, "date"], keep=False)
    quality = {"source_subset_rows": len(source), "selected_rows": len(frame), "invalid_price_rows_excluded": invalid,
        "identical_repeats_removed": repeats, "conflicting_rows_excluded": int(conflicting.sum()),
        "zero_arrival_rows_in_selected_source": int(pd.to_numeric(frame.get("Arrivals (Tonnes)", pd.Series(dtype=float)), errors="coerce").eq(0).sum()),
        "price_imputation": "None; missing targets are excluded, not filled", "grade": "Unspecified",
        "variety": "Local (reported broad category, not independently verified produce quality)"}
    accepted = normalize_frame(accepted[~conflicting])
    quality["usable_rows"] = len(accepted)
    return accepted, quality


def import_public_pilot(store: Store, source, download_manifest):
    frame, quality = normalize_public_subset(source)
    root = store.settings.data_dir / "raw" / "public_release"
    root.mkdir(parents=True, exist_ok=True)
    csv_path = store.settings.data_dir / "imports" / "real_pilot_tomato_pune.csv"
    frame.to_csv(csv_path, index=False)
    result = store.ingest(frame, "real", SOURCE, csv_path.name)
    audit = store.audit("real")
    manifest = {"source": SOURCE, "source_page": PAGE, "publisher": "Vandeet Shah", "license": "Apache 2.0",
        "download_manifest": download_manifest, "processed_at": datetime.now(timezone.utc).isoformat(),
        "requested_start": "2021-01-01", "requested_end": "2024-02-01", "quality": quality,
        "normalized_csv": str(csv_path), "coverage_audit": audit,
        "limitations": ["Third-party published historical release, not authenticated current government observations.",
            "Individual source records have not been independently reconciled against original daily government reports.",
            "Grade unreported; Local is a broad source category. No assumption of equal transaction quality.",
            "Calendar gaps include closures and missing reports; no future or spline imputation was performed."]}
    (root / "pilot_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    result.update({"quality": quality, "first_date": frame.date.min(), "last_date": frame.date.max(),
        "manifest": str(root / "pilot_manifest.json"), "series": audit["series"]})
    return result

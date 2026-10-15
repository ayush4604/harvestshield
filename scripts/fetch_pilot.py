"""Reproduce the real-data pilot, including provenance and exclusions."""
from datetime import date
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.archive import import_archive
from backend.config import Settings
from backend.data import Store, ProjectError

if __name__ == "__main__":
    store = Store(Settings.default())
    try:
        print(json.dumps(import_archive(store, date(2023, 1, 1), date(2025, 10, 30)), indent=2))
    except ProjectError as exc:
        raise SystemExit(f"CEDA archive: {exc}") from None

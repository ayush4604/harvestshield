from datetime import date
import pandas as pd
import pytest

from backend.archive import monthly_windows, normalize_archive, import_archive
from backend.config import Settings
from backend.data import ProjectError, Store


def records():
    return [{"t": "2025-01-01", "cmdty": "Tomato", "market_name": "Pune", "state_name": "Maharashtra",
        "district_name": "Pune", "variety": "Local", "p_min": 800, "p_max": 1200, "p_modal": 1000}]


def test_monthly_windows_are_complete_and_nonoverlapping():
    windows = list(monthly_windows(date(2024, 1, 15), date(2024, 3, 10)))
    assert windows == [(date(2024, 1, 15), date(2024, 1, 31)), (date(2024, 2, 1), date(2024, 2, 29)), (date(2024, 3, 1), date(2024, 3, 10))]


def test_source_normalization_preserves_variety_and_unreported_grade():
    frame, quality = normalize_archive(records(), "Maharashtra", "Pune", "Tomato", ["Pune"], "Local")
    assert frame.modal_price.iloc[0] == 1000
    assert frame.grade.iloc[0] == "Unspecified"
    assert frame.variety.iloc[0] == "Local"
    assert quality["usable"] == 1


def test_invalid_and_conflicting_archive_rows_are_excluded_not_imputed():
    good = records()[0]
    invalid = {**good, "t": "2025-01-02", "p_min": 0}
    ambiguous = {**good, "p_modal": 1100}
    another = {**good, "t": "2025-01-03"}
    frame, quality = normalize_archive([good, invalid, ambiguous, another], "Maharashtra", "Pune", "Tomato", ["Pune"], "Local")
    assert frame.date.tolist() == ["2025-01-03"]
    assert quality["invalid_excluded"] == 1
    assert quality["conflicting_rows_excluded"] == 2


def test_unknown_source_fields_fail_closed():
    with pytest.raises(ProjectError, match="missing"):
        normalize_archive([{"date": "2025-01-01"}], "Maharashtra", "Pune", "Tomato", ["Pune"], "Local")


def test_archive_date_range_limits(tmp_path):
    store = Store(Settings(tmp_path / "data", tmp_path / "artifacts"))
    with pytest.raises(ProjectError, match="range"):
        import_archive(store, date(2000, 1, 1), date(2025, 1, 1))


def test_archive_cap_splits_and_cached_windows_resume(tmp_path, monkeypatch):
    from backend import archive
    calls = []
    def response(path, payload=None):
        if path == "/states": return [{"census_state_name": "Maharashtra", "census_state_id": 27}]
        if path == "/commodities": return [{"commodity_disp_name": "Tomato", "commodity_id": 78}]
        if path.startswith("/districts"): return [{"census_district_name": "Pune", "census_district_id": 521}]
        calls.append(payload.copy())
        r = {**records()[0], "t": payload["start_date"]}
        return [r] * 1000 if payload["start_date"] == "2025-01-01" and payload["end_date"] == "2025-01-31" else [r]
    monkeypatch.setattr(archive, "_request", response)
    class LogoResponse:
        status_code = 404
        content = b""
    monkeypatch.setattr(archive.requests, "get", lambda *args, **kwargs: LogoResponse())
    store = Store(Settings(tmp_path / "data", tmp_path / "artifacts"))
    result = import_archive(store, date(2025, 1, 1), date(2025, 1, 31), markets=["Pune"])
    assert result["inserted"] == 2
    assert len(calls) == 3
    second = import_archive(store, date(2025, 1, 1), date(2025, 1, 31), markets=["Pune"])
    assert second["inserted"] == 0
    assert len(calls) == 3


def test_archive_long_retry_after_is_respected(monkeypatch):
    from backend import archive
    class Limited:
        status_code = 429
        headers = {"Retry-After": "3600"}
    monkeypatch.setattr(archive.requests, "get", lambda *args, **kwargs: Limited())
    monkeypatch.setattr(archive.time, "sleep", lambda value: None)
    with pytest.raises(ProjectError, match="3600 seconds"):
        archive._request("/states")

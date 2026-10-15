from datetime import timedelta
import numpy as np
import pandas as pd
import pytest

from backend.config import Settings, today_ist
from backend.data import ProjectError, Store, demo_frame
from backend.models import FEATURES, ModelService, make_features, temporal_split


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    root = tmp_path_factory.mktemp("trained")
    store = Store(Settings(root / "data", root / "artifacts"))
    store.ingest(demo_frame(days=550), "demo", "SYNTHETIC test observations")
    service = ModelService(store)
    report = service.train("demo")
    return service, report


def test_exact_calendar_targets_not_seventh_next_record(tmp_path):
    store = Store(Settings(tmp_path / "data", tmp_path / "artifacts"))
    df = demo_frame(days=60)
    omitted = df.date.iloc[35]
    df = df[df.date != omitted]
    store.ingest(df, "demo", "test")
    features = make_features(store.frame("demo"))
    before = pd.Timestamp(omitted) - pd.Timedelta(days=7)
    assert features[features.date == before].target_price.isna().all()
    assert ((features.target_date - features.date).dt.days == 7).all()


def test_features_do_not_change_when_future_prices_change(tmp_path):
    store = Store(Settings(tmp_path / "data", tmp_path / "artifacts"))
    store.ingest(demo_frame(days=180), "demo", "test")
    raw = store.frame("demo")
    cutoff = raw.date.sort_values().unique()[90]
    original = make_features(raw)
    changed = raw.copy()
    changed.loc[changed.date > cutoff, "modal_price"] *= 2
    modified = make_features(changed)
    left = original[original.date <= pd.Timestamp(cutoff)][["series_id", "date", *FEATURES]].reset_index(drop=True)
    right = modified[modified.date <= pd.Timestamp(cutoff)][["series_id", "date", *FEATURES]].reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)


def test_temporal_embargo_and_shared_periods(trained):
    service, _ = trained
    train, val, test = temporal_split(make_features(service.store.frame("demo")))
    assert train.target_date.max() < val.date.min()
    assert val.target_date.max() < test.date.min()
    assert train.date.max() < val.date.min()
    assert val.date.max() < test.date.min()


def test_evaluation_provenance_and_finite_predictions(trained):
    service, report = trained
    assert report["synthetic"] is True
    assert report["test_risk"]["rows"] > 30
    assert np.isfinite(report["test_regression"]["mae"])
    result = service.forecasts("demo")
    assert len(result["items"]) == 4
    assert all(r["forecast_price"] > 0 and 0 <= r["drop_probability"] <= 1 for r in result["items"])
    assert all(r["interval_low"] <= r["interval_high"] for r in result["items"])


def test_stale_forecasts_withheld(trained):
    service, _ = trained
    result = service.forecasts("demo", as_of=today_ist() + timedelta(days=4))
    assert not result["items"]
    assert len(result["withheld"]) == 4


def costs(service):
    return [{"series_id": r["series_id"], "transport_cost": 1000, "market_fees": 200} for r in service.forecasts("demo")["items"][:2]]


def test_cost_units_and_revenue(trained):
    service, _ = trained
    result = service.compare("demo", 10, costs(service))
    for row in result["rows"]:
        assert row["estimated_net_revenue"] == round(row["forecast_price"] * 10 - 1200, 2)
    assert result["rows"][0]["estimated_net_revenue"] >= result["rows"][1]["estimated_net_revenue"]


def test_duplicate_market_and_negative_cost_rejected(trained):
    service, _ = trained
    selections = costs(service)
    with pytest.raises(ProjectError, match="repeated"):
        service.compare("demo", 10, [selections[0], selections[0]])
    selections[0]["transport_cost"] = -1
    with pytest.raises(ProjectError, match="nonnegative"):
        service.compare("demo", 10, selections)


def test_cross_variety_and_date_comparison_rejected(trained, monkeypatch):
    service, _ = trained
    forecasts = service.forecasts("demo")
    selections = costs(service)
    selected = {s["series_id"] for s in selections}
    chosen = [r for r in forecasts["items"] if r["series_id"] in selected]
    chosen[0]["variety"] = "Different variety"
    monkeypatch.setattr(service, "forecasts", lambda mode: {"items": chosen})
    with pytest.raises(ProjectError, match="same crop"):
        service.compare("demo", 10, selections)
    chosen[0]["variety"] = chosen[1]["variety"]
    chosen[0]["forecast_date"] = "2000-01-01"
    with pytest.raises(ProjectError, match="forecast date"):
        service.compare("demo", 10, selections)


def test_historical_replay_excludes_later_observations(trained):
    service, report = trained
    replay = pd.Timestamp(report["splits"]["test"]["start"]).date() + timedelta(days=10)
    result = service.forecasts("demo", as_of=replay, historical=True)
    assert result["historical_replay"]
    assert len(result["items"]) == 4
    assert all(pd.Timestamp(r["observation_date"]).date() <= replay for r in result["items"])
    assert all(pd.Timestamp(r["forecast_date"]).date() == replay + timedelta(days=7) for r in result["items"])


def test_replay_rejects_training_period_to_prevent_future_trained_models(trained):
    service, report = trained
    with pytest.raises(ProjectError, match="held-out"):
        service.forecasts("demo", as_of=pd.Timestamp(report["splits"]["train"]["end"]).date(), historical=True)


def test_replay_predictions_unchanged_by_future_records(trained, monkeypatch):
    service, report = trained
    replay = pd.Timestamp(report["splits"]["test"]["start"]).date() + timedelta(days=10)
    before = service.forecasts("demo", as_of=replay, historical=True)
    raw = service.store.frame("demo")
    raw.loc[pd.to_datetime(raw.date).dt.date > replay, "modal_price"] *= 100
    monkeypatch.setattr(service.store, "frame", lambda mode: raw.copy())
    after = service.forecasts("demo", as_of=replay, historical=True)
    assert before["items"] == after["items"]


def test_unknown_grade_live_comparison_is_blocked(trained, monkeypatch):
    service, _ = trained
    forecasts = service.forecasts("demo")
    selections = costs(service)
    for item in forecasts["items"]:
        item["grade"] = "Unspecified"
    monkeypatch.setattr(service, "forecasts", lambda *args, **kwargs: forecasts)
    with pytest.raises(ProjectError, match="grade"):
        service.compare("real", 10, selections)
    result = service.compare("real", 10, selections, replay_date=today_ist())
    assert result["historical_replay"]
    assert "HISTORICAL RESEARCH" in result["note"]


def test_expanding_backtests_preserve_main_artifact(trained):
    from hashlib import sha256
    service, _ = trained
    main, _ = service.paths("demo")
    before = sha256(main.read_bytes()).hexdigest()
    result = service.backtest("demo")
    assert len(result["runs"]) == 3
    assert sha256(main.read_bytes()).hexdigest() == before
    for run in result["runs"]:
        assert run["splits"]["train"]["latest_target"] < run["splits"]["validation"]["start"]
        assert run["splits"]["validation"]["latest_target"] < run["splits"]["test"]["start"]
        assert run["splits"]["test"]["latest_target"] <= run["cutoff"]

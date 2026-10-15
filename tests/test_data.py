from datetime import timedelta
import pandas as pd
import pytest

from backend.config import Settings, today_ist
from backend.data import ProjectError, Store, demo_frame, normalize_frame, parse_csv


@pytest.fixture
def store(tmp_path):
    return Store(Settings(tmp_path / "data", tmp_path / "artifacts"))


def sample():
    return demo_frame(days=10).head(10)


def test_idempotent_and_mode_isolation(store):
    df = sample()
    assert store.ingest(df, "demo", "synthetic test")["inserted"] == 10
    assert store.ingest(df, "demo", "synthetic test")["repeated"] == 10
    assert store.frame("real").empty


def test_conflict_rolls_back_entire_import(store):
    df = sample()
    store.ingest(df.iloc[[1]], "real", "test only")
    conflicting = df.iloc[:2].copy()
    conflicting.loc[1, "modal_price"] += 1
    with pytest.raises(ProjectError, match="conflicting"):
        store.ingest(conflicting, "real", "test only")
    assert len(store.frame("real")) == 1


@pytest.mark.parametrize("column,value", [("modal_price", 0), ("modal_price", float("inf")), ("unit", "INR/kg"), ("date", "not-a-date"), ("market", "")])
def test_invalid_contract(column, value):
    df = sample()
    df.loc[0, column] = value
    with pytest.raises(ProjectError):
        normalize_frame(df)


def test_future_observation_rejected():
    df = sample()
    df.loc[0, "date"] = str(today_ist() + timedelta(days=1))
    with pytest.raises(ProjectError, match="future"):
        normalize_frame(df)


def test_rejects_inverted_prices():
    df = sample()
    df.loc[0, "min_price"] = df.loc[0, "max_price"] + 1
    with pytest.raises(ProjectError, match="min_price"):
        normalize_frame(df)


def test_conflicting_duplicate_input():
    df = sample().iloc[[0]].copy()
    duplicate = df.copy()
    duplicate.modal_price += 1
    with pytest.raises(ProjectError, match="Conflicting"):
        normalize_frame(pd.concat([df, duplicate]))


def test_csv_alias_and_day_first_dates():
    df = sample().rename(columns={"date": "Arrival_Date"})
    df["Arrival_Date"] = pd.to_datetime(df["Arrival_Date"]).dt.strftime("%d/%m/%Y")
    normalized = parse_csv(df.to_csv(index=False).encode())
    assert normalized.date.iloc[0] == sample().date.iloc[0]


def test_audit_exact_labels_and_missing_dates(store):
    df = sample().drop(index=3)
    store.ingest(df, "demo", "test")
    item = store.audit("demo")["series"][0]
    assert item["calendar_gap_days"] == 1
    assert item["seven_day_label_count"] == 3

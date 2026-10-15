"""Integration checks on the installed published pilot, if present.

Tests do not call external providers or count fixture results as field evidence.
"""
from datetime import date
from pathlib import Path
import json

from fastapi.testclient import TestClient
import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest
from urllib.parse import urlsplit

from backend.api import create_app
from backend.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def real_client(tmp_path_factory):
    history = ROOT / "data" / "imports" / "real_pilot_tomato_pune.csv"
    if not history.exists():
        pytest.skip("Published pilot not installed; run scripts/import_public_history.py first.")
    tmp = tmp_path_factory.mktemp("real-replay")
    app = create_app(Settings(tmp / "data", tmp / "artifacts"))
    frame = pd.read_csv(history)
    app.state.store.ingest(frame, "real", "Vandeet Shah / Kaggle published historical pilot; integration test")
    app.state.models.train("real")
    with TestClient(app) as client:
        yield client


def test_real_archive_stale_now_and_replay_api_works(real_client):
    current = real_client.get("/api/forecasts?mode=real").json()
    assert not current["items"]
    assert len(current["withheld"]) == 4
    period = real_client.get("/api/report?mode=real").json()["splits"]["test"]
    replay = real_client.get("/api/forecasts", params={"mode": "real", "replay_date": period["end"]})
    assert replay.status_code == 200
    data = replay.json()
    assert data["historical_replay"]
    assert len(data["items"]) >= 2
    first_date = data["items"][0]["forecast_date"]
    selected = [r for r in data["items"] if r["forecast_date"] == first_date]
    assert len(selected) >= 2
    comparison = real_client.post("/api/compare", json={"mode": "real", "replay_date": period["end"], "quantity_quintals": 10,
        "markets": [{"series_id": r["series_id"], "transport_cost": 100, "market_fees": 50} for r in selected]})
    assert comparison.status_code == 200
    assert "HISTORICAL RESEARCH" in comparison.json()["note"]
    assert real_client.get("/api/forecasts?mode=real&replay_date=2021-01-01").status_code == 400


def test_real_replay_frontend_and_stale_banner(real_client, monkeypatch):
    class Adapter:
        def __init__(self, response):
            self.response = response
            self.ok = response.status_code < 300
        def json(self): return self.response.json()
    def route(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return Adapter(real_client.request(method, urlsplit(url).path, **kwargs))
    monkeypatch.setattr(requests, "request", route)
    ui = AppTest.from_file(str(ROOT / "frontend" / "app.py"), default_timeout=30).run()
    ui.selectbox[0].set_value("Real · imported records").run()
    assert not ui.exception
    assert any("HISTORICAL DATA ONLY" in w.value for w in ui.warning)
    ui.radio[0].set_value("Forecasts").run()
    ui.checkbox[0].set_value(True).run()
    assert not ui.exception
    assert any("HISTORICAL REPLAY" in w.value for w in ui.warning)
    assert len(ui.metric) >= 6
    ui.radio[0].set_value("Market comparison").run()
    ui.checkbox[0].set_value(True).run()
    assert not ui.exception
    next(b for b in ui.button if b.label == "Compare estimated net revenue").click().run()
    assert not ui.exception
    assert any("estimated_net_revenue" in table.value.columns for table in ui.dataframe)

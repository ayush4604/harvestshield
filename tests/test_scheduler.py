"""Offline deterministic checks for automatic production collection."""
import threading
import json

from fastapi.testclient import TestClient
import pytest

from backend.api import create_app
from backend.config import Settings
from backend.data import Store, demo_frame
from backend.scheduler import FeedCollector, FeedSchedule


@pytest.fixture
def store(tmp_path):
    return Store(Settings(tmp_path / "data", tmp_path / "artifacts", environment="production", read_only=True))


def test_environment_defaults_and_validation(monkeypatch):
    assert FeedSchedule.from_environment("production").enabled
    assert not FeedSchedule.from_environment("local").enabled
    monkeypatch.setenv("HARVESTSHIELD_REFRESH_SECONDS", "1")
    with pytest.raises(ValueError, match="900"):
        FeedSchedule.from_environment("production")
    monkeypatch.setenv("HARVESTSHIELD_REFRESH_SECONDS", "21600")
    monkeypatch.setenv("HARVESTSHIELD_AUTO_REFRESH", "maybe")
    with pytest.raises(ValueError, match="true or false"):
        FeedSchedule.from_environment("production")


def test_missing_key_and_disabled_do_not_fetch(store, monkeypatch):
    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    collector = FeedCollector(store, FeedSchedule(True), threading.Lock())
    assert collector.status()["state"] == "missing_key"
    assert not collector.run_once(1000)
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-only")
    disabled = FeedCollector(store, FeedSchedule(False), threading.Lock())
    assert disabled.status()["state"] == "disabled"
    assert not disabled.run_once(1000)


def test_ingestion_restart_deadline_and_idempotence(store, monkeypatch):
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-only")
    frame = demo_frame(days=1).copy()
    frame["state"] = "Maharashtra"
    frame["market"] = ["Test market " + str(i) for i in range(4)]
    def fetch(target, state, crop, market, pages):
        assert (state, crop, market, pages) == ("Maharashtra", "Tomato", "", 3)
        return target.ingest(frame, "real", "Test fixture only, not real market evidence")
    monkeypatch.setattr("backend.scheduler.refresh_feed", fetch)
    collector = FeedCollector(store, FeedSchedule(True), threading.Lock())
    assert collector.run_once(1000)
    assert collector.status()["inserted"] == 4
    assert store.audit("real")["rows"] == 4
    assert store.audit("demo")["rows"] == 0
    restarted = FeedCollector(store, FeedSchedule(True), threading.Lock())
    assert not restarted.run_once(1001)
    assert restarted.run_once(22600)
    assert restarted.status()["inserted"] == 0
    assert restarted.status()["repeated"] == 4


def test_safe_errors_backoff_success_recovery_and_lock(store, monkeypatch, caplog):
    secret = "never-expose-test-credential"
    monkeypatch.setenv("DATA_GOV_API_KEY", secret)
    def fail(*args):
        raise RuntimeError("https://provider/?api-key=" + secret)
    monkeypatch.setattr("backend.scheduler.refresh_feed", fail)
    lock = threading.Lock()
    collector = FeedCollector(store, FeedSchedule(True), lock)
    with lock:
        assert not collector.run_once(1000)
    assert collector.run_once(1000)
    assert collector.status()["state"] == "error"
    assert not collector.run_once(1899)
    assert collector.run_once(1900)
    assert collector.status()["failures"] == 2
    assert not collector.run_once(3699)
    assert secret not in str(collector.status()) + caplog.text
    monkeypatch.setattr("backend.scheduler.refresh_feed", lambda *args: {"inserted": 0, "repeated": 4, "page_limit_reached": True})
    assert collector.run_once(3700)
    assert collector.status()["state"] == "success"
    assert collector.status()["failures"] == 0
    assert collector.status()["page_limit_reached"]


def test_configuration_change_runs_immediately(store, monkeypatch):
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-only")
    monkeypatch.setattr("backend.scheduler.refresh_feed", lambda *args: {"inserted": 0, "repeated": 0})
    first = FeedCollector(store, FeedSchedule(True), threading.Lock())
    first.run_once(1000)
    changed = FeedCollector(store, FeedSchedule(True, commodity="Onion"), threading.Lock())
    assert changed.status()["last_success"] is None
    assert changed.run_once(1001)


def test_lifespan_collects_without_exposing_write_endpoints(store, monkeypatch):
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-only")
    completed = threading.Event()
    def fetch(*args):
        completed.set()
        return {"inserted": 0, "repeated": 0}
    monkeypatch.setattr("backend.scheduler.refresh_feed", fetch)
    app = create_app(store.settings)
    with TestClient(app) as client:
        assert completed.wait(2)
        assert client.get("/api/feed/status").status_code == 200
        assert client.post("/api/feed/refresh", json={}).status_code == 403
        assert client.get("/ready").status_code == 200
    assert not app.state.collector.thread.is_alive()


def test_full_connector_ingestion_and_failure_preserves_data(store, monkeypatch):
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-only")
    row = {"arrival_date": "14/10/2026", "state": "Maharashtra", "district": "Pune",
        "market": "Test market", "commodity": "Tomato", "variety": "Local", "grade": "Local",
        "min_price": "1000", "max_price": "2000", "modal_price": "1500"}
    # Avoid dependence on the test machine's calendar.
    from backend.config import today_ist
    row["arrival_date"] = str(today_ist())
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield json.dumps({"records": [row]}).encode()
    monkeypatch.setattr("backend.feed.requests.get", lambda *args, **kwargs: Response())
    collector = FeedCollector(store, FeedSchedule(True), threading.Lock())
    assert collector.run_once(1000)
    assert collector.status()["inserted"] == 1
    assert store.frame("real").iloc[0].modal_price == 1500
    success_time = collector.status()["last_success"]
    def fail(*args, **kwargs):
        import requests
        raise requests.Timeout("secret provider URL")
    monkeypatch.setattr("backend.feed.requests.get", fail)
    assert collector.run_once(22600)
    assert collector.status()["state"] == "error"
    assert collector.status()["last_success"] == success_time
    assert store.audit("real")["rows"] == 1
    assert collector.status()["inserted"] == 1

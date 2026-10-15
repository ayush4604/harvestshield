from fastapi.testclient import TestClient
import pytest
import requests

from backend.api import create_app
from backend.config import Settings
from backend.data import ProjectError, Store, demo_frame
from backend.feed import refresh_feed


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(tmp_path / "data", tmp_path / "artifacts")))


def test_health_and_openapi(client):
    assert client.get("/health").json()["service"] == "harvestshield"
    assert "/api/train" in client.get("/openapi.json").json()["paths"]


def test_import_audit_and_history(client):
    df = demo_frame(days=12).head(12)
    response = client.post("/api/import", files={"file": ("test.csv", df.to_csv(index=False).encode(), "text/csv")}, data={"source": "Synthetic fixture for API testing only"})
    assert response.status_code == 200
    assert response.json()["inserted"] == 12
    assert client.get("/api/audit?mode=real").json()["rows"] == 12
    assert client.get("/api/audit?mode=demo").json()["rows"] == 0
    assert len(client.get("/api/history?mode=real&limit=3").json()["records"]) == 3


def test_validation_and_missing_models(client):
    assert client.get("/api/audit?mode=bogus").status_code == 422
    assert client.get("/api/forecasts?mode=real").status_code == 409
    assert client.post("/api/compare", json={"quantity_quintals": -1, "markets": []}).status_code == 422
    assert client.post("/api/import", files={"file": ("test.pkl", b"x")}, data={"source": "test"}).status_code == 400
    assert client.post("/api/train", json={"mode": "real"}).status_code == 400


def test_demo_bootstrap_is_idempotent(client):
    assert client.post("/api/demo").json()["inserted"] == 4380
    assert client.post("/api/demo").json()["inserted"] == 0


def test_feed_without_key(client, monkeypatch):
    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    response = client.post("/api/feed/refresh", json={"state": "Maharashtra", "commodity": "Tomato"})
    assert response.status_code == 409
    assert "not set" in response.json()["detail"]


def test_feed_errors_never_expose_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GOV_API_KEY", "PRIVATE_TEST_KEY")
    def fail(*args, **kwargs):
        raise requests.Timeout("https://api.example/?api-key=PRIVATE_TEST_KEY")
    monkeypatch.setattr("backend.feed.requests.get", fail)
    store = Store(Settings(tmp_path / "data", tmp_path / "artifacts"))
    with pytest.raises(ProjectError) as caught:
        refresh_feed(store, "Maharashtra", "Tomato")
    assert "PRIVATE_TEST_KEY" not in str(caught.value)
    assert "timed out" in str(caught.value)
    assert store.frame("real").empty


def test_feed_normalization_and_ignored_filter_defense(tmp_path, monkeypatch):
    import json
    rows = demo_frame(days=2).head(2).rename(columns={"date": "arrival_date"}).drop(columns=["unit"]).to_dict("records")
    rows[0]["state"] = "Other State"
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield json.dumps({"records": rows}).encode()
    monkeypatch.setenv("DATA_GOV_API_KEY", "PRIVATE_TEST_KEY")
    def fetch(*args, **kwargs):
        assert kwargs["headers"]["User-Agent"] == "HarvestShield/1.0"
        assert kwargs["headers"]["Accept"] == "application/json"
        return Response()
    monkeypatch.setattr("backend.feed.requests.get", fetch)
    store = Store(Settings(tmp_path / "data", tmp_path / "artifacts"))
    result = refresh_feed(store, "Demo State", "Tomato")
    assert result["inserted"] == 1
    assert store.frame("real").state.eq("Demo State").all()

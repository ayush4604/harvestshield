"""Exercise Streamlit pages against a real in-process FastAPI application."""
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest
import requests
from streamlit.testing.v1 import AppTest

from backend.api import create_app
from backend.config import Settings
from backend.data import demo_frame

APP_FILE = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    root = tmp_path_factory.mktemp("ui")
    app = create_app(Settings(root / "data", root / "artifacts"))
    app.state.store.ingest(demo_frame(days=550), "demo", "SYNTHETIC frontend test")
    app.state.models.train("demo")
    with TestClient(app) as client:
        yield client


@pytest.fixture
def ui(app_client, monkeypatch):
    class Adapter:
        def __init__(self, response):
            self.response = response
            self.ok = 200 <= response.status_code < 300
        def json(self):
            return self.response.json()
    def route(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return Adapter(app_client.request(method, urlsplit(url).path, **kwargs))
    monkeypatch.setattr(requests, "request", route)
    return AppTest.from_file(str(APP_FILE), default_timeout=30).run()


def test_overview_and_forecasts_render(ui):
    assert not ui.exception
    assert ui.title[0].value == "Overview"
    assert ui.metric[1].value == "2,200"
    ui.radio[0].set_value("Forecasts").run()
    assert not ui.exception
    assert len(ui.metric) >= 12
    assert any("DEMONSTRATION" in w.value for w in ui.warning)


def test_comparison_form_uses_api(ui):
    ui.radio[0].set_value("Market comparison").run()
    assert not ui.exception
    ui.number_input[0].set_value(12.0)
    ui.number_input[1].set_value(500.0)
    next(b for b in ui.button if b.label == "Compare estimated net revenue").click().run()
    assert not ui.exception
    table = ui.dataframe[0].value
    assert "estimated_net_revenue" in table
    assert len(table) == 4


def test_workspace_and_empty_real_mode(ui):
    ui.radio[0].set_value("Data & models").run()
    assert not ui.exception
    assert any(b.label == "Train models and generate report" for b in ui.button)
    ui.selectbox[0].set_value("Real · imported records").run()
    assert not ui.exception
    assert next(b for b in ui.button if b.label == "Train models and generate report").disabled
    ui.radio[0].set_value("Overview").run()
    assert not ui.exception
    assert ui.metric[1].value == "0"


def test_backend_unavailable_is_actionable(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("test")
    monkeypatch.setattr(requests, "request", fail)
    ui = AppTest.from_file(str(APP_FILE), default_timeout=15).run()
    assert not ui.exception
    assert any("Backend connection unavailable" in e.value for e in ui.error)


@pytest.mark.parametrize("policy", [{"read_only": True}, {"admin_auth_required": True}])
def test_shared_dashboard_never_exposes_admin_controls(ui, monkeypatch, policy):
    original = requests.request
    def protected_health(method, url, **kwargs):
        response = original(method, url, **kwargs)
        if urlsplit(url).path == "/health":
            data = response.json()
            data.update(policy)
            response.json = lambda: data
        return response
    monkeypatch.setattr(requests, "request", protected_health)
    ui.radio[0].set_value("Data & models").run()
    assert not ui.exception
    for label in ("Load synthetic demonstration", "Train models and generate report", "Run three expanding-window backtests"):
        assert next(b for b in ui.button if b.label == label).disabled
    ui.selectbox[0].set_value("Real · imported records").run()
    assert not ui.exception
    for label in ("Validate and import", "Fetch reported daily prices"):
        assert next(b for b in ui.button if b.label == label).disabled

"""Credential-safe provider diagnostics and current documented filter names."""
import json
import threading

import pytest
import requests

from backend.config import Settings
from backend.data import Store, demo_frame
from backend.feed import FeedError, refresh_feed
from backend.scheduler import FeedCollector, FeedSchedule


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_GOV_API_KEY", "private-test-credential")
    return Store(Settings(tmp_path / "data", tmp_path / "artifacts"))


class Response:
    def __init__(self, code=200, body=b'{}'):
        self.status_code, self.body = code, body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size): yield self.body


@pytest.mark.parametrize("status,code", [(400, "HTTP_400"), (401, "HTTP_401"),
    (403, "HTTP_403"), (429, "HTTP_429"), (503, "HTTP_OTHER"), (302, "HTTP_OTHER")])
def test_http_diagnostics_safe_and_persisted(store, monkeypatch, caplog, status, code):
    monkeypatch.setattr("backend.feed.requests.get", lambda *args, **kwargs:
        Response(status, b'private-test-credential https://provider/?api-key=private-test-credential'))
    collector = FeedCollector(store, FeedSchedule(True), threading.Lock())
    assert collector.run_once(1000)
    result = collector.status()
    assert result["error_code"] == code
    assert result["upstream_status"] == status
    assert code in caplog.text
    assert "private-test-credential" not in str(result) + caplog.text
    assert store.audit("real")["rows"] == 0


@pytest.mark.parametrize("exception,code", [(requests.Timeout, "TIMEOUT"),
    (requests.ConnectionError, "CONNECTION"), (requests.exceptions.SSLError, "TLS")])
def test_network_diagnostics_never_expose_url(store, monkeypatch, exception, code):
    def fail(*args, **kwargs):
        raise exception("https://provider/?api-key=private-test-credential")
    monkeypatch.setattr("backend.feed.requests.get", fail)
    with pytest.raises(FeedError) as caught:
        refresh_feed(store, "Maharashtra", "Tomato")
    assert caught.value.code == code
    assert "private-test-credential" not in str(caught.value)


@pytest.mark.parametrize("body,code", [(b"<html>blocked</html>", "INVALID_JSON"),
    (b'{"error":"private-test-credential"}', "SCHEMA"),
    (b'{"records":[]}', "NO_RECORDS"), (b'x' * (5 * 1024 * 1024 + 1), "TOO_LARGE")],
    ids=["html", "schema", "empty", "oversize"])
def test_body_diagnostics(store, monkeypatch, body, code):
    monkeypatch.setattr("backend.feed.requests.get", lambda *args, **kwargs: Response(body=body))
    with pytest.raises(FeedError) as caught:
        refresh_feed(store, "Maharashtra", "Tomato")
    assert caught.value.code == code
    assert "private-test-credential" not in str(caught.value)


@pytest.mark.parametrize("value", ['"private-test-credential"', "https://provider/?api-key=secret",
    "${{shared.UNRESOLVED}}", "key with spaces"])
def test_bad_environment_value_fails_before_request(store, monkeypatch, value):
    monkeypatch.setenv("DATA_GOV_API_KEY", value)
    with pytest.raises(FeedError) as caught:
        refresh_feed(store, "Maharashtra", "Tomato")
    assert caught.value.code == "KEY_FORMAT"
    assert value not in str(caught.value)


def test_documented_state_filter_and_validation_diagnostic(store, monkeypatch):
    rows = demo_frame(days=1).head(1).to_dict("records")
    def fetch(*args, **kwargs):
        assert kwargs["params"]["filters[state.keyword]"] == "Demo State"
        assert "filters[state]" not in kwargs["params"]
        assert kwargs["allow_redirects"] is False
        return Response(body=json.dumps({"records": rows}).encode())
    monkeypatch.setattr("backend.feed.requests.get", fetch)
    assert refresh_feed(store, "Demo State", "Tomato")["inserted"] == 1
    rows[0]["modal_price"] = -100
    with pytest.raises(FeedError) as caught:
        refresh_feed(store, "Demo State", "Tomato")
    assert caught.value.code == "INVALID_RECORDS"
    assert store.audit("real")["rows"] == 1


def test_conflicting_revision_preserves_existing_data(store, monkeypatch):
    rows = demo_frame(days=1).head(1).to_dict("records")
    monkeypatch.setattr("backend.feed.requests.get", lambda *args, **kwargs:
        Response(body=json.dumps({"records": rows}).encode()))
    refresh_feed(store, "Demo State", "Tomato")
    rows[0]["modal_price"] += 1
    with pytest.raises(FeedError) as caught:
        refresh_feed(store, "Demo State", "Tomato")
    assert caught.value.code == "DATA_CONFLICT"

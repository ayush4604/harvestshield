"""Git-context image seeds and single-service runtime contracts."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.config import Settings
from backend.data import Store
from backend.models import ModelService
from deployment.build_seed import prepare_image_seed
from deployment.bootstrap import initialize, port_number, api_command, ui_command, serve_web
from scripts.prepare_release import prepare_seed


def test_missing_git_seed_builds_only_synthetic_data(tmp_path):
    seed = tmp_path / "image-seed"
    assert prepare_image_seed(seed, tmp_path / "absent-prepared-seed") == "synthetic"
    state = tmp_path / "state"
    assert initialize(seed, state)
    store = Store(Settings(state / "data", state / "artifacts"))
    assert store.audit("real")["rows"] == 0
    assert store.audit("demo")["rows"] == 4380
    models = ModelService(store)
    report = models.report("demo")
    assert report["synthetic"] is True
    assert len(models.forecasts("demo")["items"]) == 4


def test_prepared_seed_is_preserved_and_partial_seed_is_rejected(tmp_path):
    prepared = prepare_seed(tmp_path / "source", allow_empty=True)
    destination = tmp_path / "copied"
    assert prepare_image_seed(destination, prepared) == "prepared"
    assert (destination / "manifest.json").read_bytes() == (prepared / "manifest.json").read_bytes()
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "unexpected").write_text("preserve")
    with pytest.raises(ValueError, match="incomplete"):
        prepare_image_seed(tmp_path / "reject", incomplete)
    with pytest.raises(ValueError, match="already exists"):
        prepare_image_seed(destination)


@pytest.mark.parametrize("value", ["0", "80", "65536", "not-a-port", None])
def test_host_port_validation(value):
    with pytest.raises(ValueError, match="PORT"):
        port_number(value)


def test_role_commands_bind_expected_ports():
    assert port_number("8080") == 8080
    api = api_command(9010, "127.0.0.1")
    ui = ui_command(8080)
    assert api[api.index("--port") + 1] == "9010"
    assert api[api.index("--host") + 1] == "127.0.0.1"
    assert ui[ui.index("--server.port") + 1] == "8080"
    assert ui[ui.index("--server.enableXsrfProtection") + 1] == "true"


def test_single_service_supervises_both_children(monkeypatch):
    backend, frontend = Mock(), Mock()
    backend.poll.return_value = None
    frontend.poll.return_value = 3
    frontend.returncode = 3
    launch = Mock(side_effect=[backend, frontend])
    response = Mock()
    response.__enter__ = Mock(return_value=Mock(status=200))
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("deployment.bootstrap.subprocess.Popen", launch)
    monkeypatch.setattr("deployment.bootstrap.urlopen", lambda *args, **kwargs: response)
    monkeypatch.setattr("deployment.bootstrap.signal.signal", lambda *args: None)
    monkeypatch.delenv("HARVESTSHIELD_INTERNAL_PORT", raising=False)
    monkeypatch.setenv("HARVESTSHIELD_API_URL", "http://invalid.example")
    assert serve_web(8080) == 3
    assert launch.call_count == 2
    backend.terminate.assert_called_once()
    import os
    assert os.environ["HARVESTSHIELD_API_URL"] == "http://127.0.0.1:8000"


def test_single_service_rejects_port_collision(monkeypatch):
    monkeypatch.setenv("HARVESTSHIELD_INTERNAL_PORT", "8080")
    with pytest.raises(ValueError, match="differ"):
        serve_web(8080)


def test_docker_build_does_not_require_ignored_seed():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    assert "COPY --chown=10001:10001 deployment/seed /seed" not in dockerfile
    assert "python -m deployment.build_seed --output /seed" in dockerfile
    assert '"deployment.bootstrap", "web"' in dockerfile
    assert "!deployment/build_seed.py" in (root / ".dockerignore").read_text()

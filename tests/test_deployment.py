"""Deployment controls use isolated state and never call external providers."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from backend.api import create_app
from backend.config import Settings
from backend.data import Store, demo_frame, ProjectError
from backend.models import ModelService
from deployment.bootstrap import initialize
from scripts.prepare_release import package, prepare_seed


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path / "data", tmp_path / "artifacts", environment="production", read_only=True)


@pytest.mark.parametrize("path", ["demo", "train", "backtest", "import", "feed/refresh"])
def test_production_read_only_blocks_all_writes_before_parsing(settings, path):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/" + path, content=b"invalid body")
        assert response.status_code == 403
        assert client.get("/api/audit?mode=real").json()["rows"] == 0


def test_read_only_keeps_reads_comparison_and_readiness(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/api/template").status_code == 200
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        # Invalid comparison is validated normally, rather than blocked as a write.
        assert client.post("/api/compare", json={}).status_code == 422
        assert client.get("/health").json()["read_only"] is True
        assert client.get("/health", headers={"host": "attacker.invalid"}).status_code == 400


def test_production_writes_require_strong_token(settings):
    with pytest.raises(ValueError, match="32"):
        replace(settings, read_only=False)
    with pytest.raises(ValueError, match="wildcard"):
        replace(settings, allowed_hosts=("*",))
    token = "test-only-long-administrator-token-123456789"
    enabled = replace(settings, read_only=False, admin_token=token)
    assert token not in repr(enabled)
    with TestClient(create_app(enabled)) as client:
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            assert client.post("/api/demo", headers=headers).status_code == 401
        response = client.post("/api/demo", headers={"Authorization": "Bearer " + token})
        assert response.status_code == 200
        assert token not in client.get("/health").text
        # Trailing slash cannot bypass administration restrictions.
        assert client.post("/api/train/", content=b"x").status_code == 401


def test_request_size_guard_checks_declared_and_actual_body(settings):
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/compare", content=b"x", headers={"content-length": "99999999"}).status_code == 413
        assert client.post("/api/compare", content=b"x", headers={"content-length": "nonsense"}).status_code == 400
        assert client.post("/api/compare", content=b"x" * (1024 * 1024 + 1), headers={"content-length": "0"}).status_code == 413


def test_readiness_fails_without_usable_storage(settings, monkeypatch):
    app = create_app(settings)
    def unavailable():
        raise sqlite3.OperationalError("private filesystem detail")
    monkeypatch.setattr(app.state.store, "connection", unavailable)
    with TestClient(app) as client:
        result = client.get("/ready")
        assert result.status_code == 503
        assert "private filesystem detail" not in result.text


def test_security_headers(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Cache-Control"] == "no-store"


def test_snapshot_market_rows_do_not_block_training_cohort(tmp_path):
    store = Store(Settings(tmp_path / "data", tmp_path / "artifacts"))
    frame = demo_frame(days=200)
    store.ingest(frame, "real", "synthetic test fixture")
    last = frame.tail(1)
    for i in range(25):
        store.ingest(last.assign(market=f"New fixture market {i}"), "real", "one-report fixture")
    service = ModelService(store)
    selected, excluded = service.training_frame("real")
    assert selected.series_id.nunique() == 4
    assert len(excluded) == 25
    chosen = selected.series_id.iloc[0]
    focused, _ = service.training_frame("real", [chosen])
    assert focused.series_id.nunique() == 1
    with pytest.raises(ProjectError, match="not present"):
        service.training_frame("real", ["unknown"])
    with pytest.raises(ProjectError, match="distinct"):
        service.training_frame("real", [chosen, chosen])


def test_snapshot_only_dataset_cannot_be_trained(tmp_path):
    store = Store(Settings(tmp_path / "data", tmp_path / "artifacts"))
    store.ingest(demo_frame(days=1), "real", "synthetic one-day fixture")
    with pytest.raises(ProjectError, match="120 exact"):
        ModelService(store).training_frame("real")


def test_seed_backup_bootstrap_and_archive_exclude_secrets(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    store = Store(Settings(root / "data", root / "artifacts"))
    store.ingest(demo_frame(days=10), "real", "SYNTHETIC seed test")
    (root / ".env").write_text("PRIVATE_TEST_KEY=secret")
    (root / "backend").mkdir()
    (root / "backend" / "api.py").write_text("# fixture")
    (root / ".streamlit").mkdir()
    (root / ".streamlit" / "secrets.toml").write_text("key='secret'")
    (root / "AGENTS.md").write_text("private local instructions")
    (root / "docs").mkdir()
    (root / "docs" / "PLAN.md").write_text("private planning notes")
    (root / "docs" / "DEPLOYMENT.md").write_text("public deployment instructions")
    seed = prepare_seed(root)
    manifest = json.loads((seed / "manifest.json").read_text())
    assert "data/harvestshield.sqlite" in manifest["files"]
    state = tmp_path / "state"
    assert initialize(seed, state) is True
    loaded = Store(Settings(state / "data", state / "artifacts"))
    assert loaded.audit("real")["rows"] == 40
    assert initialize(seed, state) is False
    archive = package(tmp_path / "release.zip", root)
    with ZipFile(archive) as z:
        assert all(not n.endswith((".env", "secrets.toml")) for n in z.namelist())
        assert "HarvestShield/deployment/seed/manifest.json" in z.namelist()
        assert "HarvestShield/docs/DEPLOYMENT.md" in z.namelist()
        assert "HarvestShield/docs/PLAN.md" not in z.namelist()
        assert "HarvestShield/AGENTS.md" not in z.namelist()
    with pytest.raises(ValueError, match="already exists"):
        prepare_seed(root)


def test_seed_corruption_and_traversal_fail_before_loading(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "manifest.json").write_text(json.dumps({"files": {"../escape": "wrong"}}))
    with pytest.raises(ValueError, match="path"):
        initialize(seed, tmp_path / "state")
    (seed / "file").write_bytes(b"changed")
    (seed / "manifest.json").write_text(json.dumps({"files": {"file": sha256(b"original").hexdigest()}}))
    with pytest.raises(ValueError, match="checksum"):
        initialize(seed, tmp_path / "state")
    assert not (tmp_path / "state").exists()


def test_partial_volume_requires_recovery(tmp_path):
    seed = prepare_seed(tmp_path / "source", allow_empty=True)
    state = tmp_path / "state"
    state.mkdir()
    (state / "partial-file").write_text("keep me")
    with pytest.raises(ValueError, match="partially"):
        initialize(seed, state)
    assert (state / "partial-file").read_text() == "keep me"


def test_interrupted_seed_with_database_but_no_marker_is_not_accepted(tmp_path):
    seed = prepare_seed(tmp_path / "source", allow_empty=True)
    state = tmp_path / "state"
    (state / "data").mkdir(parents=True)
    (state / "data" / "harvestshield.sqlite").write_bytes(b"partial database")
    with pytest.raises(ValueError, match="partially"):
        initialize(seed, state)

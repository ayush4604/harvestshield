"""Verify the deployment seed, inference and production safety using isolated state."""
from datetime import date
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.config import Settings
from deployment.bootstrap import initialize


def check(seed):
    with tempfile.TemporaryDirectory(prefix="harvest-preflight-") as tmp:
        state = Path(tmp) / "state"
        initialize(Path(seed), state)
        settings = Settings(state / "data", state / "artifacts", environment="production", read_only=True)
        app = create_app(settings)
        checks = {"model_modes": {}, "warnings": []}
        with TestClient(app) as client:
            assert client.get("/ready").status_code == 200
            assert client.post("/api/train", json={"mode": "real"}).status_code == 403
            assert client.get("/docs").status_code == 404
            for mode in ("demo", "real"):
                audit = client.get("/api/audit", params={"mode": mode}).json()
                report = client.get("/api/report", params={"mode": mode})
                if report.status_code != 200:
                    if audit["rows"]:
                        raise ValueError("Seed observations exist without a usable matching model.")
                    checks["warnings"].append(f"No {mode} observations/model in this seed.")
                    continue
                evidence = report.json()
                replay_date = evidence["splits"]["test"]["end"]
                response = client.get("/api/forecasts", params={"mode": mode, "replay_date": replay_date})
                assert response.status_code == 200 and response.json()["items"]
                items = response.json()["items"]
                costs = [{"series_id": item["series_id"], "transport_cost": 500, "market_fees": 100} for item in items[:2]]
                comparison = client.post("/api/compare", json={"mode": mode, "replay_date": replay_date, "quantity_quintals": 10, "markets": costs})
                assert comparison.status_code == 200
                checks["model_modes"][mode] = {"stored_rows": audit["rows"], "replay_date": replay_date,
                    "replay_forecasts": len(items), "comparison_rows": len(comparison.json()["rows"])}
                checks["warnings"].extend(evidence.get("warnings", []))
        checks["status"] = "passed"
        checks["container_runtime_tested"] = False
        return checks


if __name__ == "__main__":
    print(json.dumps(check(ROOT / "deployment" / "seed"), indent=2))

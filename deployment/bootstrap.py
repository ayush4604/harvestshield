"""Initialize a new persistent volume from a verified, trusted release snapshot."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


def initialize(seed: Path, state: Path):
    manifest = json.loads((seed / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    for relative, digest in files.items():
        target = (seed / relative).resolve()
        if not target.is_relative_to(seed.resolve()) or Path(relative).is_absolute():
            raise ValueError("Invalid seed manifest path.")
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("Release seed checksum mismatch.")
    database = state / "data" / "harvestshield.sqlite"
    marker = state / ".harvest-initialized.json"
    if database.exists():
        if not marker.exists() or json.loads(marker.read_text(encoding="utf-8")).get("format") != 1:
            raise ValueError("Persistent state is partially initialized. Restore a coherent backup before starting.")
        return False  # Never overwrite a deployment's database or models on restart.
    state.mkdir(parents=True, exist_ok=True)
    # Refuse ambiguous partially populated volumes instead of mixing generations.
    if any(state.iterdir()):
        raise ValueError("Persistent state is partially initialized. Restore a coherent backup before starting.")
    for relative in files:
        destination = state / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed / relative, destination)
    marker.write_text(json.dumps({"format": 1, "initial_seed_files": len(files)}), encoding="utf-8")
    return True


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "api"
    if role == "api":
        initialize(Path(os.getenv("HARVESTSHIELD_SEED_DIR", "/seed")), Path(os.getenv("HARVESTSHIELD_STATE_DIR", "/state")))
        command = [sys.executable, "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "32", "--timeout-keep-alive", "5"]
    elif role == "ui":
        command = [sys.executable, "-m", "streamlit", "run", "frontend/app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true", "--server.enableCORS", "true", "--server.enableXsrfProtection", "true", "--server.maxUploadSize", "20", "--browser.gatherUsageStats", "false"]
    else:
        raise SystemExit("Expected api or ui role.")
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()

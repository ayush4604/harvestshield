"""Initialize a new persistent volume from a verified, trusted release snapshot."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import signal
import subprocess
import time
from urllib.request import urlopen
from urllib.error import URLError


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


def port_number(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError("PORT must be an integer between 1024 and 65535.") from None
    if not 1024 <= port <= 65535:
        raise ValueError("PORT must be an integer between 1024 and 65535.")
    return port


def api_command(port=8000, host="0.0.0.0"):
    return [sys.executable, "-m", "uvicorn", "backend.api:app", "--host", host,
            "--port", str(port), "--workers", "1", "--limit-concurrency", "32", "--timeout-keep-alive", "5"]


def ui_command(port=8501):
    return [sys.executable, "-m", "streamlit", "run", "frontend/app.py", "--server.address", "0.0.0.0",
            "--server.port", str(port), "--server.headless", "true", "--server.enableCORS", "true",
            "--server.enableXsrfProtection", "true", "--server.maxUploadSize", "20", "--browser.gatherUsageStats", "false"]


def serve_web(public_port):
    """Supervise the internal API and public UI; stop both when either exits."""
    internal = port_number(os.getenv("HARVESTSHIELD_INTERNAL_PORT", "8001" if public_port == 8000 else "8000"))
    if internal == public_port:
        raise ValueError("The internal API port must differ from PORT.")
    os.environ["HARVESTSHIELD_API_URL"] = f"http://127.0.0.1:{internal}"
    children = []
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        backend = subprocess.Popen(api_command(internal, "127.0.0.1"))
        children.append(backend)
        deadline = time.monotonic() + 60
        while not stopping:
            if backend.poll() is not None:
                return backend.returncode or 1
            try:
                with urlopen(f"http://127.0.0.1:{internal}/ready", timeout=1) as response:
                    if response.status == 200:
                        break
            except (URLError, TimeoutError, OSError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Internal backend did not become ready within 60 seconds.")
            time.sleep(0.2)
        if stopping:
            return 0
        children.append(subprocess.Popen(ui_command(public_port)))
        while not stopping:
            for child in children:
                if child.poll() is not None:
                    return child.returncode or 1
            time.sleep(0.2)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "web"
    if role not in ("api", "ui", "web"):
        raise SystemExit("Expected web, api or ui role.")
    port = port_number(os.getenv("PORT", "8000" if role == "api" else "8501"))
    if role in ("api", "web"):
        state = Path(os.getenv("HARVESTSHIELD_STATE_DIR", "/state"))
        os.environ["HARVESTSHIELD_DATA_DIR"] = str(state / "data")
        initialize(Path(os.getenv("HARVESTSHIELD_SEED_DIR", "/seed")), state)
    if role == "web":
        raise SystemExit(serve_web(port))
    if role == "api":
        command = api_command(port)
    else:
        command = ui_command(port)
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()

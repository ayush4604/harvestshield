"""Build a secret-free, checksummed release and a consistent SQLite backup.

Only explicit application paths are packaged. No raw download archives, personal
submission documents, virtualenvs, credentials, logs or browser state are included.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import Settings
from backend.data import Store

DIRECTORIES = ("backend", "frontend", "tests", "scripts", "deployment", "docs", "LICENSES", ".streamlit", ".github")
ROOT_FILES = ("README.md", "AGENTS.md", "requirements.txt", "requirements-lock.txt", "pytest.ini", "Dockerfile", "compose.yaml", ".dockerignore", ".gitignore", ".env.example", "Start-HarvestShield.ps1", "Stop-HarvestShield.ps1", "Setup-HarvestShield.ps1", "Start-HarvestShield.cmd", "Stop-HarvestShield.cmd", "Prepare-Real-Pilot.cmd")


def prepare_seed(root=ROOT, allow_empty=False):
    root = Path(root)
    seed = root / "deployment" / "seed"
    if seed.exists():
        raise ValueError("Release seed already exists. Use a new staging checkout or archive the old seed first.")
    source = root / "data" / "harvestshield.sqlite"
    if not source.exists() and not allow_empty:
        raise ValueError("No project database. Import data first, or use --allow-empty for CI only.")
    with tempfile.TemporaryDirectory(prefix="harvest-release-") as tmp:
        stage = Path(tmp)
        if source.exists():
            destination = stage / "data" / "harvestshield.sqlite"
            destination.parent.mkdir()
            # SQLite online backup is consistent even when the local app is running.
            with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as src, closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Database integrity check failed.")
        else:
            Store(Settings(stage / "data", stage / "artifacts"))
        for mode in ("demo", "real"):
            for name in ("model.joblib", "evaluation.json"):
                artifact = root / "artifacts" / mode / name
                if artifact.exists():
                    dest = stage / "artifacts" / mode / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(artifact, dest)
            summary = root / "artifacts" / "backtests" / mode / "summary.json"
            if summary.exists():
                dest = stage / "artifacts" / "backtests" / mode / "summary.json"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(summary, dest)
        for name in ("publisher_metadata.json", "download_manifest.json"):
            evidence = root / "data" / "raw" / "public_release" / name
            if evidence.exists():
                dest = stage / "provenance" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(evidence, dest)
        files = {f.relative_to(stage).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
                 for f in sorted(stage.rglob("*")) if f.is_file()}
        manifest = {"format": 1, "created_at": datetime.now(timezone.utc).isoformat(), "files": files,
                    "warning": "Checksums detect corruption, not malicious replacement. Load only trusted project-owned model artifacts."}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        seed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, seed)
    return seed


def package(destination, root=ROOT):
    root, destination = Path(root), Path(destination)
    if destination.exists():
        raise ValueError("Release archive already exists. Choose a new filename.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    selected = []
    for directory in DIRECTORIES:
        folder = root / directory
        if folder.exists():
            selected.extend(f for f in folder.rglob("*") if f.is_file()
                            and "__pycache__" not in f.parts
                            and f.suffix not in (".pyc", ".log")
                            and f.name not in ("secrets.toml", "RESUME_TOMORROW.md", "CONTEXT.md"))
    selected.extend(root / name for name in ROOT_FILES if (root / name).is_file())
    template = root / "data" / "templates" / "market_history.csv"
    if template.exists():
        selected.append(template)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for file in sorted(set(selected)):
            archive.write(file, "HarvestShield/" + file.relative_to(root).as_posix())
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-empty", action="store_true", help="CI only: allow an empty database seed")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--package-only", action="store_true", help="Package an already prepared seed without replacing it")
    args = parser.parse_args()
    try:
        if args.package_only:
            if not args.archive or not (ROOT / "deployment" / "seed" / "manifest.json").is_file():
                raise ValueError("Package-only needs an archive destination and an existing seed.")
        else:
            seed = prepare_seed(allow_empty=args.allow_empty)
            print("Created verified release seed:", seed)
        if args.archive:
            print("Created deployment archive:", package(args.archive))
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Release preparation failed: {type(exc).__name__}. Check the staging inputs; existing seeds are never overwritten.\n")


if __name__ == "__main__":
    main()

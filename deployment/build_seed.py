"""Use a prepared seed, or build an offline, explicitly synthetic demo seed."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from backend.config import Settings
from backend.data import Store, demo_frame
from backend.models import ModelService


def prepare_image_seed(destination: Path, prepared: Path | None = None):
    if destination.exists():
        raise ValueError("Image seed destination already exists.")
    if prepared is not None and (prepared / "manifest.json").is_file():
        shutil.copytree(prepared, destination)
        return "prepared"
    if prepared is not None and prepared.exists() and any(prepared.iterdir()):
        raise ValueError("Prepared seed is incomplete. Refusing to replace it with demo data.")
    with tempfile.TemporaryDirectory(prefix="harvest-image-seed-") as temporary:
        stage = Path(temporary)
        store = Store(Settings(stage / "data", stage / "artifacts"))
        store.ingest(demo_frame(), "demo", "SYNTHETIC: fictional demonstration generated during image build; seed 42")
        ModelService(store).train("demo")
        files = {file.relative_to(stage).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
                 for file in sorted(stage.rglob("*")) if file.is_file()}
        (stage / "manifest.json").write_text(json.dumps({"format": 1, "files": files,
            "source": "Synthetic demonstration only. No real observations are generated."}, indent=2), encoding="utf-8")
        shutil.copytree(stage, destination)
    return "synthetic"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, default=Path(__file__).resolve().parent / "seed")
    args = parser.parse_args()
    print("Image seed:", prepare_image_seed(args.output, args.prepared))

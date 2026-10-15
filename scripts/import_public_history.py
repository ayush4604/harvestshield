"""Download only Tomato.csv from a licensed public dataset; never the 4.7 GB bundle.

This is a published historical release, not a verified current government feed.
Raw archive, metadata, checksum and selected source rows are retained.
"""
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.parse import quote
import zipfile

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import Settings
from backend.data import ProjectError
from backend.data import Store
from backend.public_history import import_public_pilot

SLUG = "vandeetshah/india-commodity-wise-mandi-dataset"
PAGE = "https://www.kaggle.com/datasets/" + SLUG
BASE = "https://www.kaggle.com/api/v1/datasets"


def download(settings):
    root = settings.data_dir / "raw" / "public_release"
    root.mkdir(parents=True, exist_ok=True)
    metadata_file = root / "publisher_metadata.json"
    if (root / "Tomato.zip").exists() and metadata_file.exists():
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    else:
        response = requests.get(BASE + "/view/" + SLUG, timeout=(5, 25))
        if response.status_code != 200:
            raise ProjectError(f"Publisher metadata returned HTTP {response.status_code}.")
        metadata = response.json()
    if metadata.get("isPrivate") or metadata.get("licenseName") != "Apache 2.0":
        raise ProjectError("Unexpected dataset access or license. Review the publisher's metadata.")
    (root / "publisher_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    token = None
    target = None
    for _ in range(3):
        params = {"pageSize": 200}
        if token:
            params["pageToken"] = token
        listing = requests.get(BASE + "/list/" + SLUG, params=params, timeout=(5, 25)).json()
        target = next((f for f in listing.get("datasetFiles", []) if f.get("name") == "Tomato.csv"), None)
        if target:
            break
        token = listing.get("nextPageToken")
        if not token:
            break
    if not target or target.get("totalBytes", 0) > 500_000_000:
        raise ProjectError("Tomato.csv not found or exceeds the bounded download size.")
    archive = root / "Tomato.zip"
    url = BASE + "/download/" + SLUG + "/" + quote("Tomato.csv")
    if not archive.exists():
        print(f"Downloading Tomato.csv only (publisher size {target['totalBytes']:,} bytes).", flush=True)
        partial = archive.with_suffix(".partial")
        size = 0
        with requests.get(url, timeout=(10, 45), stream=True) as response:
            if response.status_code != 200:
                raise ProjectError(f"Public file download returned HTTP {response.status_code}.")
            with partial.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > 500_000_000:
                        raise ProjectError("Download exceeded 500 MB limit.")
                    output.write(chunk)
        if not zipfile.is_zipfile(partial):
            raise ProjectError("Download was not a ZIP archive; access may require a user login.")
        partial.replace(archive)
    with zipfile.ZipFile(archive) as zipped:
        member = next((m for m in zipped.infolist() if Path(m.filename).name == "Tomato.csv"), None)
        if member is None or member.file_size > 500_000_000:
            raise ProjectError("Expected CSV missing or exceeds uncompressed size limit.")
        frames, read_rows = [], 0
        with zipped.open(member) as source:
            for chunk in pd.read_csv(source, chunksize=100_000, low_memory=False):
                if not read_rows:
                    print("Source columns:", chunk.columns.tolist(), flush=True)
                    print("Sample:", chunk.head(2).to_dict("records"), flush=True)
                if not {"State Name", "District Name"}.issubset(chunk.columns):
                    raise ProjectError("Published CSV identity schema changed.")
                read_rows += len(chunk)
                frame = chunk[(chunk["State Name"] == "Maharashtra") & (chunk["District Name"] == "Pune")].copy()
                if not frame.empty:
                    frames.append(frame)
        if not frames:
            raise ProjectError("No Pune records found in public release.")
    subset = pd.concat(frames, ignore_index=True)
    subset_file = settings.data_dir / "imports" / "public_tomato_pune_source.csv"
    subset.to_csv(subset_file, index=False)
    with archive.open("rb") as source:
        digest = sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    manifest = {"publisher": "Vandeet Shah", "source_page": PAGE, "license": "Apache 2.0",
        "version": metadata.get("currentVersionNumber"), "publisher_updated": metadata.get("lastUpdated"),
        "description": metadata.get("description"), "archive_sha256": digest.hexdigest(),
        "archive_file": str(archive), "source_rows_read": read_rows, "pune_rows": len(subset),
        "subset_file": str(subset_file), "provenance_limit": "Public publisher's historical market-data release; not independently verified against original daily government reports."}
    (root / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    print(subset.groupby(["Market Name", "Variety"]).size().to_string(), flush=True)
    return subset, manifest


if __name__ == "__main__":
    settings = Settings.default()
    settings.prepare()
    root = settings.data_dir / "raw" / "public_release"
    subset_path = settings.data_dir / "imports" / "public_tomato_pune_source.csv"
    try:
        if subset_path.exists() and (root / "download_manifest.json").exists():
            subset = pd.read_csv(subset_path)
            manifest = json.loads((root / "download_manifest.json").read_text(encoding="utf-8"))
        else:
            subset, manifest = download(settings)
        print(json.dumps(import_public_pilot(Store(settings), subset, manifest), indent=2))
    except ProjectError as exc:
        raise SystemExit(f"Published history: {exc}") from None
    except (requests.RequestException, ValueError, zipfile.BadZipFile):
        raise SystemExit("Published history download or format unavailable. Existing database/model artifacts are retained.") from None

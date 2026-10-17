"""Recover missing deck images from explicitly cited title/artist source overrides."""

from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path

from PIL import Image

from tools.common import read_json, state_records, write_json
from tools.commons_upgrades import Client, license_fields

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--overrides", type=Path, default=ROOT / "catalog/source-overrides.json")
    args = parser.parse_args()
    # Reversed so the first note wins when a title/artist pair repeats.
    paintings = reversed(read_json(args.catalog)["paintings"])
    catalog = {(p["title"], p["artist"]): p for p in paintings}
    folder = ROOT / "data/curated-masters"
    folder.mkdir(parents=True, exist_ok=True)
    state_path = ROOT / "data/curated-upgrades/state.json"
    state = state_records(state_path)
    client = Client(delay=1)
    for override in read_json(args.overrides)["paintings"]:
        painting = catalog[override["title"], override["artist"]]
        identity = painting["id"]
        if state.get(identity, {}).get("status") == "accepted":
            continue
        info = client.file_info(override["fileTitle"], iiprop="url|size|mime|extmetadata")
        raw = client.get(info["url"], maximum=64_000_000)
        with Image.open(io.BytesIO(raw)) as image:
            width, height, fmt = image.width, image.height, image.format
            image.draft("RGB", (4096, 4096))
            image.load()
        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(fmt or "")
        if suffix is None:
            raise ValueError(f"Unsupported source image format: {fmt}")
        path = folder / (identity + suffix)
        path.write_bytes(raw)
        state[identity] = {
            "status": "accepted",
            "id": identity,
            "master_path": str(path.resolve()),
            "candidate_dimensions": [width, height],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "method": "title/artist/date identity checked against cited source; no original deck image available",
            "reason": override["reason"],
            "evidenceUrl": override["evidenceUrl"],
            "selected": {
                "sourceUrl": info.get("descriptionurl", override["evidenceUrl"]),
                "downloadUrl": info["url"],
                **license_fields(info),
            },
        }
        write_json(state_path, {"records": state}, compact=True)
        print(painting["title"], width, height, flush=True)


if __name__ == "__main__":
    main()

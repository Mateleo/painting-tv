"""Recover missing deck images from explicitly cited title/artist source overrides."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.parse
from pathlib import Path

from PIL import Image

from tools.commons_upgrades import API, Client, atomic_json
from tools.painting_catalog import strip_html

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--overrides", type=Path, default=ROOT / "catalog/source-overrides.json")
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())["paintings"]
    overrides = json.loads(args.overrides.read_text())["paintings"]
    folder = ROOT / "data/curated-masters"
    folder.mkdir(parents=True, exist_ok=True)
    state_path = ROOT / "data/curated-upgrades/state.json"
    state = json.loads(state_path.read_text()).get("records", {}) if state_path.exists() else {}
    client = Client(delay=1)
    for override in overrides:
        painting = next(
            p
            for p in catalog
            if p["title"] == override["title"] and p["artist"] == override["artist"]
        )
        identity = painting["id"]
        if state.get(identity, {}).get("status") == "accepted":
            continue
        query = urllib.parse.urlencode(
            {
                "action": "query",
                "format": "json",
                "titles": override["fileTitle"],
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
            }
        )
        payload = json.loads(client.get(API + "?" + query))
        page = next(iter(payload["query"]["pages"].values()))
        info = page["imageinfo"][0]
        raw = client.get(info["url"], maximum=64_000_000)
        with Image.open(io.BytesIO(raw)) as image:
            width, height, fmt = image.width, image.height, image.format
            image.draft("RGB", (4096, 4096))
            image.load()
        if fmt is None:
            raise ValueError("Source image has no recognized format")
        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt]
        path = folder / (identity + suffix)
        path.write_bytes(raw)
        meta = info.get("extmetadata", {})
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
                "license": strip_html(meta.get("LicenseShortName", {}).get("value", "")),
                "licenseUrl": meta.get("LicenseUrl", {}).get("value", ""),
                "attribution": strip_html(meta.get("Artist", {}).get("value", "")),
                "credit": strip_html(meta.get("Credit", {}).get("value", "")),
            },
        }
        atomic_json(state_path, {"records": state})
        print(painting["title"], width, height, flush=True)


if __name__ == "__main__":
    main()

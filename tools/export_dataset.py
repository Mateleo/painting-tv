"""Export the quality pack as the Hugging Face dataset folder the app downloads.

The folder holds the app's slim ``catalog.json``, the images it references, a
``metadata.jsonl`` that lets the Hub viewer browse paintings with their images
and source details, and the dataset card. Rebuilding replaces stale files.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from tools.common import enrich_collection_metadata, file_sha256, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
CATALOG_VERSION = 2
APP_FIELDS = (
    "id",
    "title",
    "artist",
    "year",
    "movement",
    "collection",
    "imageUrl",
    "width",
    "height",
    "license",
    "sourceUrl",
)


def app_entry(painting: dict[str, Any], french_titles: dict[str, str]) -> dict[str, Any]:
    """Keep only what the app reads, with the French title where the deck has an English one."""
    item = {key: painting[key] for key in APP_FIELDS if painting.get(key) not in (None, "")}
    item["title"] = french_titles.get(painting["id"], painting.get("title", ""))
    return item


def viewer_row(entry: dict[str, Any], painting: dict[str, Any], image: Path) -> dict[str, Any]:
    selection = painting.get("sourceSelection", {})
    return {
        "file_name": entry["imageUrl"],
        **{
            key: entry.get(key, "")
            for key in ("id", "title", "artist", "year", "movement", "collection")
        },
        "width": entry.get("width", 0),
        "height": entry.get("height", 0),
        "source": selection.get("source", ""),
        "source_url": entry.get("sourceUrl", ""),
        "license": entry.get("license", ""),
        "license_url": selection.get("licenseUrl", ""),
        "attribution": selection.get("attribution", ""),
        "credit": selection.get("credit", ""),
        "bytes": image.stat().st_size,
        "sha256": file_sha256(image),
    }


def place(source: Path, target: Path) -> None:
    """Hard-link the pack image when possible; the dataset folder then costs no extra space."""
    if target.exists():
        if os.path.samefile(source, target):
            return
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def export_dataset(pack: Path, output: Path, titles: Path, card: Path) -> dict[str, int]:
    paintings = enrich_collection_metadata(read_json(pack / "catalog.json")["paintings"])
    french_titles = read_json(titles) if titles.exists() else {}
    entries, rows, kept = [], [], set()
    for painting in paintings:
        entry = app_entry(painting, french_titles)
        source = pack / entry["imageUrl"]
        if not source.is_file():
            raise FileNotFoundError(f"Missing pack image for {entry['id']}: {source}")
        target = output / entry["imageUrl"]
        place(source, target)
        kept.add(target.resolve())
        entries.append(entry)
        rows.append(viewer_row(entry, painting, target))
    for stale in (output / "images").rglob("*"):
        if stale.is_file() and stale.resolve() not in kept:
            stale.unlink()
    write_json(
        output / "catalog.json", {"version": CATALOG_VERSION, "paintings": entries}, compact=True
    )
    lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    (output / "metadata.jsonl").write_text(lines, encoding="utf-8")
    shutil.copyfile(card, output / "README.md")
    return {
        "paintings": len(entries),
        "frenchTitles": sum(e["id"] in french_titles for e in entries),
        "withCollection": sum("collection" in e for e in entries),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=ROOT / "data/tv-quality-pack")
    parser.add_argument("--output", type=Path, default=ROOT / "data/hf-upload")
    parser.add_argument("--titles", type=Path, default=ROOT / "catalog/titles-fr.json")
    parser.add_argument("--card", type=Path, default=ROOT / "tools/dataset-card.md")
    args = parser.parse_args()
    print(export_dataset(args.pack, args.output, args.titles, args.card))


if __name__ == "__main__":
    main()

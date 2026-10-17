"""Sequential technical audit of the local painting image collection.

The metrics here describe files and rendering fit. They do not assess artistic
quality. Run with ``python -m tools.image_quality`` from the repository root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "data/catalog.json"


def _sharpness(image: Image.Image) -> float:
    """Return a thumbnail-scale Laplacian variance heuristic."""
    gray = image.convert("L")
    gray.thumbnail((512, 512))
    # Edge response variance is an inexpensive sharpness/detail proxy.
    edges = gray.filter(ImageFilter.FIND_EDGES)
    return round(ImageStat.Stat(edges).var[0], 2)


def audit_image(path: Path, *, entry_id: str, title: str = "", artist: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": entry_id,
        "title": title,
        "artist": artist,
        "path": str(path),
        "status": "missing",
    }
    if not path.is_file():
        return result
    result.update(file_bytes=path.stat().st_size)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    result["sha256"] = digest.hexdigest()
    try:
        with Image.open(path) as image:
            fmt = image.format
            image.verify()
        with Image.open(path) as image:
            image.load()  # Full decode catches truncated/corrupt pixel data.
            width, height = image.size
            sharpness = _sharpness(image)
    except Exception as error:  # Pillow raises several decoder-specific exceptions.
        result.update(status="corrupt", error=f"{type(error).__name__}: {error}")
        return result

    scale = max(3840 / width, 2160 / height)
    crop_width = min(width, round(3840 / scale))
    crop_height = min(height, round(2160 / scale))
    flags = []
    if scale > 1.01:
        flags.append("upscale-for-4k-crop")
    if sharpness < 300:
        flags.append("low-edge-detail-heuristic")
    result.update(
        status="ok",
        format=fmt,
        width=width,
        height=height,
        megapixels=round(width * height / 1_000_000, 3),
        aspect_ratio=round(width / height, 4),
        crop_visible_width=crop_width,
        crop_visible_height=crop_height,
        crop_visible_megapixels=round(crop_width * crop_height / 1_000_000, 3),
        upscale_factor=round(scale, 3),
        tv_fit="upscale" if scale > 1.01 else "downscale-or-native",
        sharpness_heuristic=sharpness,
        flags=flags,
    )
    return result


def run_audit(
    catalog_path: Path = DEFAULT_CATALOG, *, repo_root: Path = ROOT, include_starters: bool = True
) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    items = catalog.get("paintings", [])
    records = []
    seen: dict[str, list[str]] = {}
    for painting in items:
        raw_path = painting.get("imageUrl", "")
        if not raw_path or raw_path.startswith("http"):
            raw_path = painting.get("originalImageUrl", "")
        path = (
            (catalog_path.parent / raw_path).resolve()
            if raw_path and not raw_path.startswith("http")
            else Path("/__unavailable__")
        )
        # Catalog paths are normally data-relative; absolute and traversal paths are retained faithfully.
        record = audit_image(
            path,
            entry_id=str(painting.get("id", "")),
            title=painting.get("title", ""),
            artist=painting.get("artist", ""),
        )
        record["catalog_image"] = raw_path
        if record.get("sha256"):
            seen.setdefault(record["sha256"], []).append(record["id"])
        records.append(record)
    # Include the two sample assets shipped in the Android app.
    asset_catalog = repo_root / "app/src/main/assets/catalog.json"
    if include_starters and asset_catalog.exists():
        for painting in json.loads(asset_catalog.read_text(encoding="utf-8")).get("paintings", []):
            path = repo_root / "app/src/main/assets" / painting.get("imageUrl", "")
            record = audit_image(
                path,
                entry_id=f"starter:{painting.get('id', '')}",
                title=painting.get("title", ""),
                artist=painting.get("artist", ""),
            )
            record["catalog_image"] = painting.get("imageUrl", "")
            if record.get("sha256"):
                seen.setdefault(record["sha256"], []).append(record["id"])
            records.append(record)

    good = [record for record in records if record["status"] == "ok"]
    bins = Counter()
    for record in good:
        scale = record["upscale_factor"]
        bins["native_or_better"] += scale <= 1.01
        bins["up_to_1_5x"] += 1.01 < scale <= 1.5
        bins["1_5_to_2x"] += 1.5 < scale <= 2
        bins["over_2x"] += scale > 2
    return {
        "schema_version": 1,
        "target": {"width": 3840, "height": 2160, "fit": "center-crop/fill"},
        "catalog_path": str(catalog_path),
        "record_count": len(records),
        "ok_count": len(good),
        "missing_count": sum(r["status"] == "missing" for r in records),
        "corrupt_count": sum(r["status"] == "corrupt" for r in records),
        "resolution_bins_by_required_upscale": dict(bins),
        "below_4k_crop_fraction": round(
            sum(r["upscale_factor"] > 1.01 for r in good) / len(good), 4
        )
        if good
        else 0,
        "duplicate_groups": [
            {"sha256": digest, "ids": ids} for digest, ids in seen.items() if len(ids) > 1
        ],
        "heuristic_note": "Sharpness and upscale flags are technical review cues only; they are not judgments about artwork or composition.",
        "records": records,
    }


def write_compact(report: dict[str, Any], path: Path) -> None:
    rows = [
        {
            k: item.get(k)
            for k in (
                "id",
                "status",
                "format",
                "width",
                "height",
                "file_bytes",
                "upscale_factor",
                "crop_visible_width",
                "crop_visible_height",
                "sharpness_heuristic",
                "flags",
                "catalog_image",
            )
        }
        for item in report["records"]
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema_version": 1, "record_count": len(rows), "records": rows},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=ROOT / "data/quality-audit.json")
    parser.add_argument("--compact", type=Path, default=ROOT / "catalog/image-quality-audit.json")
    parser.add_argument(
        "--no-starters",
        action="store_true",
        help="Audit only the selected collection, excluding bundled starter artwork",
    )
    args = parser.parse_args(argv)
    report = run_audit(args.catalog, include_starters=not args.no_starters)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_compact(report, args.compact)
    print(
        f"Audited {report['record_count']} records: {report['ok_count']} readable, {report['missing_count']} missing, {report['corrupt_count']} corrupt"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

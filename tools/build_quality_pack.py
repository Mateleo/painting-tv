"""Merge verified larger sources, export TV images, and report every catalog record."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
from pathlib import Path
from typing import Any

from tools.common import read_json, state_records, write_json
from tools.image_quality import run_audit
from tools.optimize_images import build_pack

ROOT = Path(__file__).resolve().parents[1]


def merge_sources(
    catalog_path: Path,
    wikiart_path: Path,
    commons_path: Path,
    output: Path,
    *,
    curated_path: Path | None = None,
    reviewed_path: Path | None = None,
    research_path: Path | None = None,
) -> dict[str, Any]:
    catalog = read_json(catalog_path)
    # (selection label, report key, base for relative masters, records); absent files add none.
    sources = [
        (kind, key, path.parent if path else ROOT, state_records(path))
        for kind, key, path in (
            ("WikiArt", "wikiartRecordsChecked", wikiart_path),
            ("Wikimedia Commons", "commonsRecordsChecked", commons_path),
            ("Wikimedia Commons (curated)", "curatedRecordsChecked", curated_path),
            ("WikiArt (visual review)", "modelVisualReviews", reviewed_path),
            ("Researched source", "researchRecordsChecked", research_path),
        )
    ]
    paintings = []
    origins = collections.Counter()
    for painting in catalog["paintings"]:
        identity = painting["id"]
        item = dict(painting)
        original = painting.get("originalImageUrl", painting.get("imageUrl", ""))
        original_path = (
            (catalog_path.parent / original).resolve()
            if original and "://" not in original
            else None
        )
        candidates = []
        for kind, _, base, records in sources:
            record = records.get(identity, {})
            if record.get("status") != "accepted":
                continue
            master = Path(record.get("master_path", ""))
            if not master.is_absolute():
                master = base / master
            if not master.is_file():
                continue
            width, height = record["candidate_dimensions"]
            candidates.append(
                (min(width / 3840, height / 2160), width * height, kind, master.resolve(), record)
            )
        if candidates:
            _, _, kind, master, record = max(candidates, key=lambda row: row[:2])
            width, height = record["candidate_dimensions"]
            selected = record.get("selected", {})
            item.update(
                imageUrl=os.path.relpath(master, output.parent),
                width=width,
                height=height,
                sourceUrl=selected.get("sourceUrl") or record.get("source_page_url", ""),
                license=selected.get("license") or record.get("source_license", ""),
            )
            item["sourceSelection"] = {
                "source": kind,
                "method": record.get("method", "automatic image comparison against deck reference"),
                "comparison": record.get("visual_match"),
                "downloadUrl": selected.get("downloadUrl") or record.get("source_image_url", ""),
                "sha256": record.get("sha256") or record.get("candidate_sha256"),
                "attribution": selected.get("attribution", ""),
                "credit": selected.get("credit", ""),
                "licenseUrl": selected.get("licenseUrl", ""),
            }
            origins[kind] += 1
        else:
            item["imageUrl"] = (
                os.path.relpath(original_path, output.parent)
                if original_path and original_path.is_file()
                else ""
            )
            item["sourceSelection"] = {
                "source": "embedded deck image",
                "method": "original fallback",
            }
            origins["embedded" if item["imageUrl"] else "missing"] += 1
        if original_path and original_path.is_file():
            item["originalImageUrl"] = os.path.relpath(original_path, output.parent)
        paintings.append(item)
    report = {
        "catalogRecords": len(paintings),
        "selectedSources": dict(origins),
        **{key: len(records) for _, key, _, records in sources},
    }
    write_json(output, {"version": 1, "paintings": paintings, "sourceReport": report})
    return report


def report_every_record(
    base_catalog: Path, selected_catalog: Path, pack: Path, output: Path
) -> dict[str, Any]:
    originals = read_json(base_catalog)["paintings"]
    selected_document = read_json(selected_catalog)
    selected = {p["id"]: p for p in selected_document["paintings"]}
    exported = {p["id"]: p for p in read_json(pack / "catalog.json")["paintings"]}
    final_audit = run_audit(pack / "catalog.json", include_starters=False)
    checked = {r["id"]: r for r in final_audit["records"]}
    rows: list[dict[str, Any]] = []
    for original in originals:
        identity = original["id"]
        picked = selected[identity]
        final = exported.get(identity)
        audit = checked.get(identity, {})
        width, height = (final["width"], final["height"]) if final else (0, 0)
        before_width = original.get("originalWidth", original.get("width")) or 0
        before_height = original.get("originalHeight", original.get("height")) or 0
        before_upscale = (
            max(3840 / before_width, 2160 / before_height)
            if before_width and before_height
            else None
        )
        row = {
            "id": identity,
            "title": original.get("title", ""),
            "artist": original.get("artist", ""),
            "status": audit.get("status", "missing"),
            "beforeWidth": before_width,
            "beforeHeight": before_height,
            "width": width,
            "height": height,
            "beforeCropUpscale": round(before_upscale, 3) if before_upscale else None,
            "cropUpscale": audit.get("upscale_factor"),
            "native4kFill": bool(width >= 3840 and height >= 2160),
            "native4kFit": bool(width >= 3840 or height >= 2160),
            "improved": bool(width * height > before_width * before_height),
            "selectedSource": picked.get("sourceSelection", {}).get("source", ""),
            "sourceUrl": picked.get("sourceUrl", ""),
            "fileBytes": audit.get("file_bytes", 0),
            "compression": final.get("compression", {}).get("formatDecision", "") if final else "",
            "flags": audit.get("flags", ["missing-source"]),
        }
        rows.append(row)
    summary = {
        "recordsChecked": len(rows),
        "readable": sum(r["status"] == "ok" for r in rows),
        "missing": sum(r["status"] == "missing" for r in rows),
        "corrupt": sum(r["status"] == "corrupt" for r in rows),
        "improved": sum(r["improved"] for r in rows),
        "native4kFill": sum(r["native4kFill"] for r in rows),
        "native4kFit": sum(r["native4kFit"] for r in rows),
        "stillNeedsEnlargementFor4kFill": sum(
            r["status"] == "ok" and not r["native4kFill"] for r in rows
        ),
        "outputBytes": sum(r["fileBytes"] for r in rows),
    }
    compression_file = pack / "compression-report.json"
    value = {
        "summary": summary,
        "sourceCoverage": selected_document.get("sourceReport", {}),
        "compression": read_json(compression_file) if compression_file.exists() else {},
        "note": "Every original record is accounted for. Technical comparisons and model visual review are not human approval. Pixel dimensions do not prove genuine fine detail.",
        "records": rows,
    }
    write_json(output, value)
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "flags": "; ".join(row["flags"])})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--wikiart", type=Path, default=ROOT / "data/upgrades/state.json")
    parser.add_argument("--commons", type=Path, default=ROOT / "data/commons-upgrades/state.json")
    parser.add_argument("--curated", type=Path, default=ROOT / "data/curated-upgrades/state.json")
    parser.add_argument("--reviewed", type=Path, default=ROOT / "data/review-upgrades/state.json")
    parser.add_argument("--research", type=Path, default=ROOT / "data/research-upgrades/state.json")
    parser.add_argument("--selected", type=Path, default=ROOT / "data/selected/catalog.json")
    parser.add_argument("--pack", type=Path, default=ROOT / "data/tv-quality-pack")
    parser.add_argument("--report", type=Path, default=ROOT / "catalog/quality-upgrade-report.json")
    parser.add_argument("--merge-only", action="store_true")
    args = parser.parse_args()
    paths = {key: value.resolve() for key, value in vars(args).items() if isinstance(value, Path)}
    merged = merge_sources(
        paths["catalog"],
        paths["wikiart"],
        paths["commons"],
        paths["selected"],
        curated_path=paths["curated"],
        reviewed_path=paths["reviewed"],
        research_path=paths["research"],
    )
    print(json.dumps(merged), flush=True)
    if args.merge_only:
        return
    print(json.dumps(build_pack(paths["selected"], paths["pack"])), flush=True)
    summary = report_every_record(
        paths["catalog"], paths["selected"], paths["pack"], paths["report"]
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()

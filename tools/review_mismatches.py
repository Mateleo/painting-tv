"""Download and prepare paired visual review sheets for source mismatches.

Uses the already-recorded WikiArt candidates; it never changes the original
source-upgrade state or promotes a file based on numerical thresholds alone.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from tools import source_upgrades
from tools.common import file_sha256, read_json, write_json
from tools.source_upgrades import MAX_IMAGE_BYTES, check_image, letterbox

ROOT = Path(__file__).resolve().parents[1]


def _load_state(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {"schema_version": 1, "records": {}}


def download_all(
    report_path: Path, catalog_path: Path, *, masters_dir: Path, state_path: Path, workers: int = 2
) -> dict[str, Any]:
    if not 1 <= workers <= 2:
        raise ValueError("workers must be 1 or 2")
    records = [
        x
        for x in read_json(report_path)["records"]
        if x.get("status") == "rejected-visual-mismatch"
    ]
    source = {str(p["id"]): p for p in read_json(catalog_path).get("paintings", [])}
    state = _load_state(state_path)
    entries = state.setdefault("records", {})
    masters_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for item in records:
        item_id = str(item["id"])
        existing = entries.get(item_id, {})
        if (
            existing.get("download_status") == "ok"
            and Path(existing.get("master_path", "")).is_file()
        ):
            continue
        painting = source.get(item_id)
        if not painting:
            entries[item_id] = {
                "download_status": "error",
                "reason": "source catalog record missing",
                "candidate": item,
            }
            continue
        ref_path = catalog_path.parent / (painting.get("imageUrl") or "")
        tasks.append((item, ref_path))

    def do_one(item: dict[str, Any], ref_path: Path) -> tuple[str, dict[str, Any]]:
        item_id = str(item["id"])
        try:
            if not item.get("source_image_url"):
                raise ValueError("candidate URL missing")
            data = source_upgrades._request(
                item["source_image_url"], max_bytes=MAX_IMAGE_BYTES, timeout=35
            )
            digest = hashlib.sha256(data).hexdigest()
            if item.get("candidate_sha256") and digest != item["candidate_sha256"]:
                raise ValueError("download SHA-256 differs from recorded source candidate")
            (width, height), fmt = check_image(data)
            fmt = fmt or "unknown"
            if not ref_path.is_file():
                raise FileNotFoundError(f"reference image missing: {ref_path}")
            suffix = ".png" if fmt == "PNG" else ".jpg"
            target = masters_dir / f"{item_id}{suffix}"
            temp = target.with_suffix(target.suffix + ".partial")
            temp.write_bytes(data)
            os.replace(temp, target)
            return item_id, {
                "download_status": "ok",
                "master_path": str(target.resolve()),
                "source_page_url": item["source_page_url"],
                "source_image_url": item["source_image_url"],
                "candidate_dimensions": [width, height],
                "candidate_format": fmt,
                "candidate_bytes": len(data),
                "candidate_sha256": digest,
                "reference_path": str(ref_path.resolve()),
                "visual_match": item.get("visual_match", {}),
                "candidate": item,
            }
        except Exception as error:
            return item_id, {
                "download_status": "error",
                "reason": f"{type(error).__name__}: {error}",
                "candidate": item,
            }

    print(
        f"Downloading {len(tasks)} review candidates; {len(entries) - len(tasks)} already recorded; workers={workers}",
        flush=True,
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(do_one, item, ref) for item, ref in tasks]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            if future.cancelled():
                continue
            item_id, result = future.result()
            entries[item_id] = result
            write_json(state_path, state, compact=True)
            if index % 12 == 0 or index == len(futures):
                print(f"Downloaded {index}/{len(futures)} candidates", flush=True)
            if source_upgrades._blocked.is_set():
                for pending in futures:
                    pending.cancel()
    write_json(state_path, state, compact=True)
    return {
        "candidate_count": len(records),
        "downloaded_count": sum(x.get("download_status") == "ok" for x in entries.values()),
        "error_count": sum(x.get("download_status") == "error" for x in entries.values()),
        "state_path": str(state_path),
    }


def _thumb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.draft("RGB", (560, 292))
        return letterbox(image, (560, 292), "#202124")


def create_contact_sheets(state_path: Path, output_dir: Path, *, per_sheet: int = 12) -> list[Path]:
    state = _load_state(state_path)
    entries = [
        (key, item)
        for key, item in state.get("records", {}).items()
        if item.get("download_status") == "ok"
    ]
    entries.sort(key=lambda pair: pair[0])
    output_dir.mkdir(parents=True, exist_ok=True)
    cell_w, cell_h = 1160, 360
    columns = 2
    rows = math.ceil(per_sheet / columns)
    font = ImageFont.load_default(size=21)
    output = []
    for start in range(0, len(entries), per_sheet):
        page = start // per_sheet + 1
        batch = entries[start : start + per_sheet]
        sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), "#101114")
        draw = ImageDraw.Draw(sheet)
        for i, (item_id, entry) in enumerate(batch):
            col, row = i % columns, i // columns
            x, y = col * cell_w, row * cell_h
            item = entry["candidate"]
            metrics = item.get("visual_match", {})
            label = f"{item_id} | {item.get('artist', '')} — {item.get('title', '')}"
            label = label[:110]
            draw.text((x + 8, y + 6), label, fill="white", font=font)
            draw.text(
                (x + 8, y + 32),
                f"ref  {metrics.get('reference_dimensions')}    cand  {entry.get('candidate_dimensions')}    aspect {metrics.get('aspect_delta_fraction')}  RMSE {metrics.get('thumbnail_rgb_rmse')}  dHash {metrics.get('dhash_distance')}",
                fill="#c7c9ce",
                font=font,
            )
            sheet.paste(_thumb(Path(entry["reference_path"])), (x + 8, y + 60))
            sheet.paste(_thumb(Path(entry["master_path"])), (x + 588, y + 60))
            draw.text((x + 10, y + 338), "LOCAL REFERENCE", fill="#9bd49b", font=font)
            draw.text((x + 590, y + 338), "WIKIART CANDIDATE", fill="#9bd49b", font=font)
        target = output_dir / f"mismatch-review-{page:02d}.jpg"
        sheet.save(target, quality=90)
        output.append(target)
    return output


def apply_decisions(review_path: Path, state_path: Path, report_path: Path) -> dict[str, int]:
    """Apply recorded model decisions only to identical, locally verified downloads."""
    review = read_json(review_path)
    state = _load_state(state_path)
    records = state.get("records", {})
    decisions = review.get("records", [])
    counts = {"accepted": 0, "rejected": 0, "stale": 0}
    for decision in decisions:
        item_id = str(decision["id"])
        entry = records.get(item_id, {})
        digest = decision.get("candidate_sha256")
        if entry.get("download_status") != "ok" or entry.get("candidate_sha256") != digest:
            entry["status"] = "needs-review"
            entry.pop("accepted", None)
            counts["stale"] += 1
            continue
        accepted = bool(decision.get("accepted"))
        dims = entry.get("candidate_dimensions") or []
        prior_match = entry.get("visual_match") or entry.get("original_visual_match") or {}
        ref_dims = prior_match.get("reference_dimensions") or []
        if accepted and (
            len(dims) != 2
            or len(ref_dims) != 2
            or not all(int(a) > int(b) for a, b in zip(dims, ref_dims))
        ):
            raise ValueError(f"accepted candidate {item_id} is not larger in both dimensions")
        master = Path(entry["master_path"])
        if accepted and not master.is_file():
            raise ValueError(f"accepted candidate {item_id} master is missing")
        if accepted:
            if file_sha256(master) != digest:
                entry["status"] = "needs-review"
                entry.pop("accepted", None)
                counts["stale"] += 1
                continue
        entry.update(
            {
                "accepted": accepted,
                "status": "accepted" if accepted else "rejected",
                "method": decision["method"],
                "reason": decision["reason"],
                "candidate_dimensions": dims,
                "visual_match": prior_match or decision.get("visual_match", {}),
                "source_page_url": entry.get("source_page_url"),
                "source_image_url": entry.get("source_image_url"),
                "candidate_sha256": digest,
            }
        )
        if accepted:
            counts["accepted"] += 1
        else:
            counts["rejected"] += 1
    write_json(state_path, state, compact=True)
    write_json(
        report_path,
        {
            "schema_version": 1,
            "method": "model visual review of paired reference and candidate thumbnails; accepted only when the same work/composition is clear and candidate dimensions are larger",
            "reviewed_count": len(decisions),
            "accepted_count": counts["accepted"],
            "rejected_count": counts["rejected"],
            "records": decisions,
        },
    )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "catalog/source-upgrades.json")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--masters", type=Path, default=ROOT / "data/review-masters")
    parser.add_argument("--state", type=Path, default=ROOT / "data/review-upgrades/state.json")
    parser.add_argument("--sheets", type=Path, default=ROOT / "data/review-sheets")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--sheets-only", action="store_true")
    parser.add_argument(
        "--apply-decisions",
        type=Path,
        help="apply an existing reviewed-source-overrides.json after validating hashes and dimensions",
    )
    parser.add_argument(
        "--decision-report", type=Path, default=ROOT / "catalog/reviewed-source-overrides.json"
    )
    args = parser.parse_args(argv)
    if not args.sheets_only:
        print(
            json.dumps(
                download_all(
                    args.report,
                    args.catalog,
                    masters_dir=args.masters,
                    state_path=args.state,
                    workers=args.workers,
                )
            ),
            flush=True,
        )
    sheets = create_contact_sheets(args.state, args.sheets) if not args.apply_decisions else []
    if args.apply_decisions:
        print(
            json.dumps(apply_decisions(args.apply_decisions, args.state, args.decision_report)),
            flush=True,
        )
    print(
        json.dumps({"contact_sheets": [str(path) for path in sheets]}, ensure_ascii=False),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

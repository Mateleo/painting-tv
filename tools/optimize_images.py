"""Prepare a high-fidelity, Android-compatible offline pack, one image at a time.

Install the optional images dependencies: python -m pip install '.[images]'.
Masters are never overwritten. No image is enlarged or AI reconstructed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import shutil
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageCms, ImageOps, ImageStat, features

ROOT = Path(__file__).resolve().parents[1]
ANDROID_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
COMPRESSION_REVISION = 3


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sample_psnr(reference: Image.Image, encoded: Path) -> float:
    """Measure five full-resolution detail patches, not a blurred thumbnail.

    PSNR is a numeric compression-error guard, not a perceptual art-quality score.
    A codec can still affect texture differently; the unchanged master is retained.
    """
    width, height = reference.size
    patch_w, patch_h = min(width, 256), min(height, 256)
    points = {(0, 0), (width - patch_w, 0), (0, height - patch_h),
              (width - patch_w, height - patch_h), ((width - patch_w) // 2, (height - patch_h) // 2)}
    squared = 0.0
    samples = 0
    with Image.open(encoded) as decoded:
        decoded.load()
        if decoded.size != reference.size:
            return 0.0
        for x, y in points:
            box = (x, y, x + patch_w, y + patch_h)
            with reference.crop(box).convert("RGB") as source, decoded.crop(box).convert("RGB") as target:
                difference = ImageChops.difference(source, target)
                stats = ImageStat.Stat(difference)
                squared += sum(v * v for v in stats.rms) * patch_w * patch_h
                samples += patch_w * patch_h * 3
                difference.close()
    mse = squared / samples
    return 100.0 if mse == 0 else 10 * math.log10(255 * 255 / mse)


def color_convert(image: Image.Image) -> tuple[Image.Image, str]:
    """Normalize profiled scans to sRGB for predictable TV colors."""
    icc = image.info.get("icc_profile")
    if icc:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            target = ImageCms.createProfile("sRGB")
            result = ImageCms.profileToProfile(image, source, target, outputMode="RGB")
            return result, "converted to sRGB from embedded ICC profile"
        except (OSError, ValueError, ImageCms.PyCMSError):
            # Preserve the profile in an untouched original rather than guessing its colors.
            return image.convert("RGB"), "unhandled ICC profile; keep original"
    return image.convert("RGB"), "assumed sRGB (no embedded ICC profile)"


def optimize_one(source: Path, destination: Path, *, quality: int = 96,
                 min_psnr: float = 43.0, max_edge: int = 0,
                 max_pixels: int = 0) -> dict[str, Any]:
    """Use WebP only when it is smaller and passes the detail-patch error guard."""
    if not features.check("webp"):
        raise RuntimeError("Pillow was built without WebP support")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".candidate.webp")
    with Image.open(source) as opened:
        source_size = opened.size
        source_format = opened.format
        transparent = "A" in opened.getbands() or "transparency" in opened.info
        if source_format not in ANDROID_FORMATS:
            raise ValueError(f"Unsupported TV image format: {source_format}")
        pixels = source_size[0] * source_size[1]
        ratio = min(1.0, max_edge / max(source_size) if max_edge else 1.0,
                    math.sqrt(max_pixels / pixels) if max_pixels else 1.0)
        size = tuple(max(1, int(value * ratio)) for value in source_size)
        resized = size != source_size
        orientation = opened.getexif().get(274, 1)
        # Already compact JPEGs rarely benefit from another high-fidelity lossy
        # generation. Retain their exact bytes before allocating decoded pixels.
        if not resized and orientation in (None, 1) and source_format == "JPEG" and (
                source.stat().st_size * 8 / pixels < 3.0 or max(source_size) > 16383):
            output = destination.with_suffix(".jpg")
            shutil.copyfile(source, output)
            return {"path": str(output), "sourceWidth": source_size[0], "sourceHeight": source_size[1],
                    "width": source_size[0], "height": source_size[1], "sourceBytes": source.stat().st_size,
                    "outputBytes": output.stat().st_size, "formatDecision": "original-kept-efficient-jpeg",
                    "samplePsnrDb": 100.0, "colorAction": "original color/profile bytes retained",
                    "resizedForTV": False, "upscaled": False}
        # JPEG's draft decoder reduces memory before the full image is allocated.
        if resized and source_format == "JPEG":
            opened.draft("RGB", size)
        opened.load()
        oriented = ImageOps.exif_transpose(opened)
        rgb, color_action = color_convert(oriented)
        if transparent:
            color_action = "transparency present; keep original"
        oriented.close()
    try:
        if resized:
            # EXIF rotations can swap dimensions; scale using the oriented geometry.
            limit = min(1.0, max_edge / max(rgb.size) if max_edge else 1.0,
                        math.sqrt(max_pixels / (rgb.width * rgb.height)) if max_pixels else 1.0)
            rgb.thumbnail(tuple(max(1, int(value * limit)) for value in rgb.size), Image.Resampling.LANCZOS)
        width, height = rgb.size
        # Palette/flat images benefit from exact lossless WebP. Photographic scans
        # use a high quality candidate, accepted only below the conservative error bound.
        lossless = source_format == "PNG"
        rgb.save(temporary, "WEBP", quality=quality, method=3, lossless=lossless, exact=True)
        psnr = sample_psnr(rgb, temporary)
        original_bytes = source.stat().st_size
        candidate_bytes = temporary.stat().st_size
        geometry_transformed = resized or orientation not in (None, 1)
        keep_original = color_action.startswith(("unhandled", "transparency"))
        acceptable = psnr >= min_psnr and not keep_original
        use_webp = acceptable and (geometry_transformed or candidate_bytes < original_bytes * 0.95)
        if use_webp:
            output = destination.with_suffix(".webp")
            temporary.replace(output)
            decision = "webp-lossless" if lossless else "webp-high-quality"
        elif geometry_transformed and not keep_original:
            # Quality beats compression: lossless export if the lossy candidate
            # misses the threshold after a required color/size/orientation transform.
            output = destination.with_suffix(".webp")
            rgb.save(output, "WEBP", lossless=True, method=3, exact=True)
            psnr = 100.0
            decision = "webp-lossless-after-transform"
        else:
            output = destination.with_suffix(ANDROID_FORMATS[source_format])
            shutil.copyfile(source, output)
            width, height = source_size
            psnr = 100.0
            decision = "original-kept"
            if color_action.startswith("converted"):
                color_action = "original embedded ICC profile retained"
        return {"path": str(output), "sourceWidth": source_size[0], "sourceHeight": source_size[1],
                "width": width, "height": height, "sourceBytes": original_bytes,
                "outputBytes": output.stat().st_size, "formatDecision": decision,
                "samplePsnrDb": round(psnr, 3), "colorAction": color_action,
                "resizedForTV": resized, "upscaled": False}
    finally:
        rgb.close()
        temporary.unlink(missing_ok=True)


def build_pack(catalog_path: Path, output: Path, *, quality: int = 96, min_psnr: float = 43.0,
               max_edge: int = 0, max_pixels: int = 0) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    items = catalog["paintings"]
    images = output / "images"
    images.mkdir(parents=True, exist_ok=True)
    state_file = output / "compression-state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    records, omitted = [], []
    options = {"quality": quality, "min_psnr": min_psnr, "max_edge": max_edge, "max_pixels": max_pixels}
    for index, painting in enumerate(items):
        identity = painting["id"]
        if not isinstance(identity, str) or not identity or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in identity):
            raise ValueError("Invalid painting ID")
        address = painting.get("imageUrl", "")
        if not address or "://" in address:
            omitted.append({"id": identity, "title": painting.get("title", ""), "reason": "no downloaded local source"})
            continue
        source = (catalog_path.parent / address).resolve()
        if not source.is_file():
            omitted.append({"id": identity, "title": painting.get("title", ""), "reason": "source file missing"})
            continue
        stamp = hashlib.sha256(json.dumps([COMPRESSION_REVISION, str(source), source.stat().st_mtime_ns,
                                          source.stat().st_size, options], sort_keys=True).encode()).hexdigest()
        entry = state.get(identity, {})
        if entry.get("stamp") != stamp or not Path(entry.get("path", "")).is_file():
            try:
                entry = optimize_one(source, images / identity, **options)
            except (OSError, ValueError) as error:
                omitted.append({"id": identity, "title": painting.get("title", ""), "reason": str(error)})
                continue
            entry["stamp"] = stamp
            state[identity] = entry
            write_json(state_file, state)
        item = {key: painting.get(key, "") for key in (
            "id", "title", "artist", "year", "movement", "imageUrl", "width", "height", "sourceUrl", "license")}
        if "sourceSelection" in painting:
            item["sourceSelection"] = {key: painting["sourceSelection"].get(key, "") for key in (
                "source", "method", "downloadUrl", "sha256", "attribution", "credit", "licenseUrl")}
        item.update(imageUrl="images/" + Path(entry["path"]).name, width=entry["width"], height=entry["height"])
        item["compression"] = {key: value for key, value in entry.items() if key not in ("path", "stamp")}
        records.append(item)
        if (index + 1) % 25 == 0:
            print(f"Compressed/checked {index + 1}/{len(items)}", flush=True)
    manifest = {"version": 1, "paintings": records}
    write_json(output / "catalog.json", manifest)
    kept = [state[item["id"]] for item in records]
    report = {"recordsChecked": len(items), "included": len(records), "omitted": omitted,
              "options": options, "sourceBytes": sum(row["sourceBytes"] for row in kept),
              "outputBytes": sum(row["outputBytes"] for row in kept),
              "webpImages": sum(row["formatDecision"].startswith("webp") for row in kept),
              "originalsKept": sum(row["formatDecision"].startswith("original-kept") for row in kept),
              "noUpscaling": True, "androidMinimum": 26,
              "guard": "Five native-resolution patches, PSNR >= min_psnr for lossy WebP; otherwise original or lossless."}
    write_json(output / "compression-report.json", report)
    bundle = output.parent / (output.name + ".zip")
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.write(output / "catalog.json", "catalog.json")
        archive.write(output / "compression-report.json", "compression-report.json")
        for item in records:
            archive.write(output / item["imageUrl"], item["imageUrl"])
    report["bundlePath"] = str(bundle)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/upgrades/catalog.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/tv-quality-pack")
    parser.add_argument("--quality", type=int, default=96)
    parser.add_argument("--min-psnr", type=float, default=43.0)
    parser.add_argument("--max-edge", type=int, default=0, help="Optional export resize limit; 0 preserves source dimensions")
    parser.add_argument("--max-pixels", type=int, default=0, help="Optional export pixel limit; 0 preserves source dimensions")
    args = parser.parse_args()
    if not 1 <= args.quality <= 100 or args.min_psnr <= 0 or (args.max_edge != 0 and args.max_edge < 256) or (args.max_pixels != 0 and args.max_pixels < 65_536):
        parser.error("Invalid compression limits")
    print(json.dumps(build_pack(args.catalog.resolve(), args.output.resolve(), quality=args.quality,
                               min_psnr=args.min_psnr, max_edge=args.max_edge, max_pixels=args.max_pixels), indent=2))


if __name__ == "__main__":
    main()

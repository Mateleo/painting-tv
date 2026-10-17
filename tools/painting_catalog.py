"""Download, extract, resolve, and package the Tableaux de maîtres Anki deck.

The module intentionally uses the Python standard library. Network work is
limited to metadata and image-header requests until the explicit ``pack``
command is used.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

DECK_ID = 171273480
ANKI_INFO = "https://ankiweb.net/svc/shared/item-info"
ANKI_DOWNLOAD = "https://ankiweb.net/svc/shared/download-deck/{deck_id}"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "PaintingTV/0.1 (https://github.com/Mateleo/painting-tv; personal art catalog)"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def request(url: str, *, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            retry = exc.headers.get("Retry-After", "")
            try:
                pause = max(1.0, min(120.0, float(retry)))
            except ValueError:
                pause = min(120.0, 2.0 ** (attempt + 1))
            time.sleep(pause)
    raise RuntimeError("HTTP retry limit exhausted")


def protobuf_fields(data: bytes):
    """Yield (field number, wire type, value) for protobuf wire data."""

    def varint(pos: int) -> tuple[int, int]:
        value = shift = 0
        while pos < len(data):
            byte = data[pos]
            pos += 1
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                return value, pos
            shift += 7
            if shift > 70:
                break
        raise ValueError("Invalid protobuf varint")

    pos = 0
    while pos < len(data):
        tag, pos = varint(pos)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("Invalid protobuf field number")
        if wire == 0:
            value, pos = varint(pos)
        elif wire == 1:
            value, pos = data[pos : pos + 8], pos + 8
        elif wire == 2:
            size, pos = varint(pos)
            value, pos = data[pos : pos + size], pos + size
        elif wire == 5:
            value, pos = data[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"Unsupported protobuf wire type {wire}")
        if pos > len(data):
            raise ValueError("Truncated protobuf field")
        yield number, wire, value


def first_field(data: bytes, number: int, wire: int = 2):
    return next((v for n, w, v in protobuf_fields(data) if n == number and w == wire), None)


def shared_deck_download_key(deck_id: int = DECK_ID) -> str:
    query = urllib.parse.urlencode({"sharedId": deck_id})
    body = request(f"{ANKI_INFO}?{query}")
    available = first_field(body, 1)
    if available is None:
        raise RuntimeError(f"AnkiWeb did not return an available deck for {deck_id}")
    deck = first_field(available, 10)
    key = first_field(deck, 5) if deck else None
    if not key:
        raise RuntimeError("AnkiWeb response did not include a deck download key")
    return key.decode("utf-8")


def download_deck(out: Path, deck_id: int = DECK_ID) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    key = shared_deck_download_key(deck_id)
    url = ANKI_DOWNLOAD.format(deck_id=deck_id) + "?" + urllib.parse.urlencode({"t": key})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = out.with_suffix(out.suffix + ".partial")
    with urllib.request.urlopen(req, timeout=180) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    if not zipfile.is_zipfile(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Downloaded file is not a valid Anki .apkg package")
    tmp.replace(out)
    return out


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<br\s*/?>", " ", value)
    value = re.sub(r"(?is)<[^>]+>", "", value)
    return html.unescape(value).strip()


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    """Read raster dimensions from headers, without decoding the full image."""
    try:
        with path.open("rb") as f:
            head = f.read(32)
            if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
                return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
            if head[:3] == b"GIF":
                return int.from_bytes(head[6:8], "little"), int.from_bytes(head[8:10], "little")
            if head[:2] == b"BM" and len(head) >= 26:
                return abs(int.from_bytes(head[18:22], "little", signed=True)), abs(
                    int.from_bytes(head[22:26], "little", signed=True)
                )
            if (
                head[:4] == b"RIFF"
                and head[8:12] == b"WEBP"
                and head[12:16] == b"VP8X"
                and len(head) >= 30
            ):
                return 1 + int.from_bytes(head[24:27], "little"), 1 + int.from_bytes(
                    head[27:30], "little"
                )
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    prefix = f.read(1)
                    if not prefix:
                        break
                    if prefix != b"\xff":
                        continue
                    marker = f.read(1)
                    while marker == b"\xff":
                        marker = f.read(1)
                    if marker in (b"\xd8", b"\xd9", b""):
                        continue
                    raw_length = f.read(2)
                    if len(raw_length) != 2:
                        break
                    length = int.from_bytes(raw_length, "big")
                    if marker[0] in (
                        0xC0,
                        0xC1,
                        0xC2,
                        0xC3,
                        0xC5,
                        0xC6,
                        0xC7,
                        0xC9,
                        0xCA,
                        0xCB,
                        0xCD,
                        0xCE,
                        0xCF,
                    ):
                        segment = f.read(5)
                        if len(segment) == 5:
                            return int.from_bytes(segment[3:5], "big"), int.from_bytes(
                                segment[1:3], "big"
                            )
                        break
                    f.seek(length - 2, 1)
    except OSError:
        pass
    return None, None


def extract_apkg(apkg: Path, out_dir: Path) -> list[dict[str, Any]]:
    """Extract deck notes and media; retain original Anki media names."""
    out_dir.mkdir(parents=True, exist_ok=True)
    media_dir = out_dir / "images"
    media_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(apkg) as archive:
        names = set(archive.namelist())
        collection_name = next(
            (
                n
                for n in ("collection.anki2", "collection.anki21", "collection.anki21b")
                if n in names
            ),
            None,
        )
        if collection_name is None:
            raise ValueError("No supported Anki collection database found")
        db_path = out_dir / ".collection.sqlite"
        db_path.write_bytes(archive.read(collection_name))
        conn = sqlite3.connect(db_path)
        try:
            model_json = json.loads(conn.execute("SELECT models FROM col LIMIT 1").fetchone()[0])
            models = {int(mid): model for mid, model in model_json.items()}
            rows = conn.execute("SELECT id, mid, flds, tags FROM notes ORDER BY id").fetchall()
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

        media_map = json.loads(archive.read("media")) if "media" in names else {}
        for archive_name, original_name in media_map.items():
            if archive_name not in names:
                continue
            safe = Path(original_name).name
            if safe and safe not in (".", ".."):
                target = media_dir / safe
                if not target.exists():
                    target.write_bytes(archive.read(archive_name))

    paintings = []
    for note_id, model_id, packed_fields, tags in rows:
        model = models.get(model_id, {})
        fields = model.get("flds", [])
        values = packed_fields.split("\x1f")
        mapping = {
            f.get("name", ""): values[i] if i < len(values) else "" for i, f in enumerate(fields)
        }
        raw_image = mapping.get("Artwork", "")
        match = re.search(r"(?i)<img\b[^>]*\bsrc\s*=\s*['\"]?([^\s>'\"]+)", raw_image)
        image_name = Path(match.group(1)).name if match else ""
        image_path = media_dir / image_name if image_name else None
        width, height = (
            image_dimensions(image_path) if image_path and image_path.exists() else (None, None)
        )
        title = strip_html(mapping.get("Title", ""))
        artist = strip_html(mapping.get("Artist", ""))
        identity = f"{note_id}:{artist}:{title}"
        paintings.append(
            {
                "id": hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16],
                "title": title,
                "artist": artist,
                "year": strip_html(mapping.get("Date", "")),
                "movement": strip_html(mapping.get("Period/Movement", "")),
                "imageUrl": f"images/{image_name}" if image_path and image_path.exists() else "",
                "width": width,
                "height": height,
                "sourceUrl": "",
                "license": "",
                "medium": strip_html(mapping.get("Medium", "")),
                "tags": strip_html(tags),
                "resolution": {"status": "unresolved", "confidence": 0.0, "candidates": []},
            }
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "catalog.json").write_text(
        json.dumps({"version": 1, "paintings": paintings}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paintings


def normalize(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def commons_candidates(painting: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    query = f"{painting['title']} {painting['artist']}".strip()
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
        }
    )
    payload = json.loads(request(f"{COMMONS_API}?{params}"))
    pages = payload.get("query", {}).get("pages", {}).values()
    target = normalize(painting["title"] + " " + painting["artist"])
    result = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") not in (None, "image/jpeg", "image/png", "image/webp"):
            continue
        title = page.get("title", "")
        text = normalize(title.replace("File:", "") + " " + page.get("snippet", ""))
        overlap = len(set(target.split()) & set(text.split())) / max(1, len(set(target.split())))
        result.append(
            {
                "source": "Wikimedia Commons",
                "title": title,
                "imageUrl": info.get("url", ""),
                "sourceUrl": "https://commons.wikimedia.org/wiki/"
                + urllib.parse.quote(title.replace(" ", "_")),
                "width": info.get("width"),
                "height": info.get("height"),
                "license": (
                    info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")
                ),
                "score": round(overlap, 3),
            }
        )
    return sorted(result, key=lambda c: c["score"], reverse=True)


def resolve_catalog(
    catalog_path: Path, *, limit: int | None = None, delay: float = 1.0, resume: bool = True
) -> int:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    paintings = catalog["paintings"]
    pending = [
        painting
        for painting in paintings
        if painting.get("resolution", {}).get("status") != "approved"
        and not (
            resume
            and painting.get("resolution", {}).get("status") in ("needs-review", "no-candidates")
        )
    ]
    if limit is not None:
        pending = pending[: max(0, limit)]
    processed = 0
    consecutive_throttles = 0
    for i, painting in enumerate(pending):
        processed += 1
        try:
            candidates = commons_candidates(painting)
            consecutive_throttles = 0
            score = candidates[0]["score"] if candidates else 0.0
            painting["resolution"] = {
                "status": "needs-review" if candidates else "no-candidates",
                "confidence": score,
                "confidenceBasis": "Approximate title and artist token overlap; score is a ranking hint, not a probability. Manual image review is required.",
                "candidates": candidates,
            }
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            painting["resolution"] = {
                "status": "lookup-error",
                "confidence": 0.0,
                "candidates": [],
                "error": str(exc),
            }
            consecutive_throttles = (
                consecutive_throttles + 1
                if isinstance(exc, urllib.error.HTTPError) and exc.code == 429
                else 0
            )
        catalog_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if consecutive_throttles >= 3:
            print("Commons is rate-limiting requests. Progress saved; resume later.")
            break
        if i + 1 < len(pending):
            time.sleep(delay)
    return processed


def export_manifest(
    catalog_path: Path, output: Path, *, online: bool = False, offline_pack: bool = False
) -> None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    root = catalog_path.parent
    paintings = []
    omitted = []
    for source in catalog["paintings"]:
        remote = source.get("imageUrl", "")
        original = source.get("originalImageUrl", remote)
        local = source.get("resolution", {}).get("offlineImage")
        use_local = (not online) or offline_pack
        image = remote if online and not offline_pack else original
        if use_local and local and (root / local).is_file():
            image = local
        if not image or (not image.startswith("https://") and not (root / image).is_file()):
            omitted.append(source)
            continue
        entry = {
            k: source.get(k, "")
            for k in (
                "id",
                "title",
                "artist",
                "year",
                "movement",
                "imageUrl",
                "width",
                "height",
                "sourceUrl",
                "license",
            )
        }
        entry["imageUrl"] = image
        if image == original and remote != original:
            entry["width"] = source.get("originalWidth", entry["width"])
            entry["height"] = source.get("originalHeight", entry["height"])
            entry["sourceUrl"] = source.get("originalSourceUrl", "")
            entry["license"] = source.get("originalLicense", "")
        if not image.startswith("https://"):
            entry["imageUrl"] = os.path.relpath(root / image, output.parent).replace("\\", "/")
        paintings.append(entry)
    if omitted:
        report = output.with_suffix(output.suffix + ".report.json")
        report.write_text(
            json.dumps(
                {
                    "omittedWithoutImage": [
                        {"id": p["id"], "title": p["title"], "artist": p["artist"]} for p in omitted
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    output.write_text(
        json.dumps({"version": 1, "paintings": paintings}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def approve_candidate(catalog_path: Path, painting_id: str, candidate_index: int = 0) -> None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    painting = next((p for p in catalog["paintings"] if p["id"] == painting_id), None)
    if painting is None:
        raise KeyError(f"Painting id not found: {painting_id}")
    candidates = painting.get("resolution", {}).get("candidates", [])
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise IndexError(f"Candidate {candidate_index} is not available for {painting_id}")
    candidate = candidates[candidate_index]
    if "originalImageUrl" not in painting:
        painting["originalImageUrl"] = painting.get("imageUrl", "")
        painting["originalWidth"] = painting.get("width", "")
        painting["originalHeight"] = painting.get("height", "")
        painting["originalSourceUrl"] = painting.get("sourceUrl", "")
        painting["originalLicense"] = painting.get("license", "")
    for key in ("imageUrl", "width", "height", "sourceUrl", "license"):
        painting[key] = candidate.get(key, "")
    painting["resolution"].pop("offlineImage", None)
    painting["resolution"].update(
        {
            "status": "approved",
            "approvedCandidate": candidate_index,
            "provenance": f"Manually approved candidate from {candidate.get('source', 'unknown source')}",
        }
    )
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def download_pack(catalog_path: Path, pack_dir: Path, *, min_width: int = 0) -> int:
    """Download manually approved source images, resuming existing files."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    pack_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for painting in catalog["paintings"]:
        url = painting.get("imageUrl", "")
        if (
            not url.startswith("https://")
            or painting.get("resolution", {}).get("status") != "approved"
        ):
            continue
        if painting.get("width") and painting["width"] < min_width:
            continue
        suffix = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
        target = pack_dir / f"{painting['id']}{suffix}"
        root = catalog_path.parent.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.resolve().is_relative_to(root):
            raise ValueError("Offline image directory must be inside the catalog data directory")
        if target.exists() and target.stat().st_size > 0:
            painting.setdefault("resolution", {})["offlineImage"] = str(
                target.relative_to(catalog_path.parent)
            )
            catalog_path.write_text(
                json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            continue
        temp = target.with_suffix(target.suffix + ".partial")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=90) as response, temp.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        if image_dimensions(temp) == (None, None):
            temp.unlink(missing_ok=True)
            raise ValueError(
                f"Downloaded file is not a supported raster image for {painting['title']}"
            )
        temp.replace(target)
        painting.setdefault("resolution", {})["offlineImage"] = str(
            target.relative_to(catalog_path.parent)
        )
        downloaded += 1
        catalog_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return downloaded


def bundle_catalog(catalog_path: Path, output: Path) -> Path:
    """Create app import ZIP with root catalog.json and all referenced images."""
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    root = catalog_path.parent
    packaged = []
    omitted = []
    for original in catalog["paintings"]:
        local = original.get("resolution", {}).get("offlineImage")
        remote = original.get("imageUrl", "")
        deck_image = original.get("originalImageUrl", remote)
        has_highres = bool(local and (root / local).is_file())
        image = local if has_highres else deck_image
        if not image or image.startswith("https://") or not (root / image).is_file():
            omitted.append(
                {
                    "id": original["id"],
                    "title": original["title"],
                    "artist": original["artist"],
                    "reason": "no embedded image available",
                }
            )
            continue
        item = {
            k: original.get(k, "")
            for k in (
                "id",
                "title",
                "artist",
                "year",
                "movement",
                "imageUrl",
                "width",
                "height",
                "sourceUrl",
                "license",
            )
        }
        if has_highres:
            suffix = (root / local).suffix or ".jpg"
            item["imageUrl"] = f"images/highres-{original['id']}{suffix}"
            item["width"] = original.get("width") or ""
            item["height"] = original.get("height") or ""
        else:
            item["imageUrl"] = deck_image
            item["width"] = original.get("originalWidth", item["width"])
            item["height"] = original.get("originalHeight", item["height"])
            if remote != deck_image:
                item["sourceUrl"] = original.get("originalSourceUrl", "")
                item["license"] = original.get("originalLicense", "")
        packaged.append(item)
    report = {"included": len(packaged), "omittedCount": len(omitted), "omitted": omitted}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "catalog.json",
            json.dumps({"version": 1, "paintings": packaged}, ensure_ascii=False, indent=2) + "\n",
        )
        archive.writestr(
            "bundle-report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        image_root = root / "images"
        if image_root.exists():
            for image in sorted(image_root.iterdir()):
                if image.is_file():
                    archive.write(image, f"images/{image.name}")
        for original in catalog["paintings"]:
            local = original.get("resolution", {}).get("offlineImage")
            if not local or not (root / local).is_file():
                continue
            target = f"images/highres-{original['id']}{(root / local).suffix or '.jpg'}"
            archive.write(root / local, target)
    output.with_suffix(output.suffix + ".report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output


def export_metadata(catalog_path: Path, output: Path) -> None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    fields = ("id", "title", "artist", "year", "movement", "medium", "tags")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "version": 1,
                "paintings": [
                    {key: p.get(key, "") for key in fields} for p in catalog["paintings"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_download = sub.add_parser("download", help="Fetch the latest shared .apkg from AnkiWeb")
    p_download.add_argument("--deck-id", type=int, default=DECK_ID)
    p_download.add_argument("--output", type=Path, default=DATA / "tableaux-de-maitres.apkg")
    p_extract = sub.add_parser("extract", help="Extract note fields and original deck images")
    p_extract.add_argument("--apkg", type=Path, default=DATA / "tableaux-de-maitres.apkg")
    p_extract.add_argument("--output", type=Path, default=DATA)
    p_resolve = sub.add_parser("resolve", help="Query Commons for reviewable image candidates")
    p_resolve.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    p_resolve.add_argument("--limit", type=int)
    p_resolve.add_argument("--delay", type=float, default=1.0)
    p_resolve.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Reuse existing candidates and only retry unresolved records (default)",
    )
    p_resolve.add_argument(
        "--refresh", action="store_false", dest="resume", help="Replace existing candidates"
    )
    p_export = sub.add_parser("manifest", help="Export app contract JSON")
    p_export.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    p_export.add_argument("--output", type=Path, default=DATA / "paintings.json")
    p_export.add_argument(
        "--online", action="store_true", help="Keep HTTPS image URLs and resolution metadata"
    )
    p_export.add_argument(
        "--offline-pack",
        action="store_true",
        help="Point at local pack files and embedded-deck fallback images",
    )
    p_pack = sub.add_parser("pack", help="Download only suggested/approved images for offline use")
    p_pack.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    p_pack.add_argument("--directory", type=Path, default=DATA / "offline-pack" / "images")
    p_pack.add_argument("--min-width", type=int, default=0)
    p_approve = sub.add_parser("approve", help="Approve a reviewed resolver candidate")
    p_approve.add_argument("painting_id")
    p_approve.add_argument("--candidate", type=int, default=0)
    p_approve.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    p_bundle = sub.add_parser(
        "bundle", help="Build an app ZIP with catalog.json at the root and all images"
    )
    p_bundle.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    p_bundle.add_argument("--output", type=Path, default=DATA / "painting-pack.zip")
    p_metadata = sub.add_parser("metadata", help="Export all note metadata without image data")
    p_metadata.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    p_metadata.add_argument("--output", type=Path, default=ROOT / "catalog" / "paintings.json")
    args = parser.parse_args()
    if args.command == "download":
        print(download_deck(args.output, args.deck_id))
    elif args.command == "extract":
        print(f"Extracted {len(extract_apkg(args.apkg, args.output))} notes")
    elif args.command == "resolve":
        print(
            f"Processed {resolve_catalog(args.catalog, limit=args.limit, delay=args.delay, resume=args.resume)} paintings"
        )
    elif args.command == "manifest":
        export_manifest(
            args.catalog, args.output, online=args.online, offline_pack=args.offline_pack
        )
        print(args.output)
    elif args.command == "pack":
        print(
            f"Downloaded {download_pack(args.catalog, args.directory, min_width=args.min_width)} images"
        )
    elif args.command == "approve":
        approve_candidate(args.catalog, args.painting_id, args.candidate)
        print(f"Approved candidate {args.candidate} for {args.painting_id}")
    elif args.command == "bundle":
        result = bundle_catalog(args.catalog, args.output)
        report = json.loads(
            result.with_suffix(result.suffix + ".report.json").read_text(encoding="utf-8")
        )
        print(
            f"{result}: included {report['included']}; omitted {report['omittedCount']} without images"
        )
    elif args.command == "metadata":
        export_metadata(args.catalog, args.output)
        print(args.output)


if __name__ == "__main__":
    main()

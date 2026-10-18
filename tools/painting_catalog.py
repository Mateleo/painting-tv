"""Download the Tableaux de maîtres Anki deck and extract its notes and images.

The module intentionally uses the Python standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
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

from tools.common import enrich_collection_metadata, read_json, write_json

DECK_ID = 171273480
ANKI_INFO = "https://ankiweb.net/svc/shared/item-info"
ANKI_DOWNLOAD = "https://ankiweb.net/svc/shared/download-deck/{deck_id}"
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
        # Newer exports add a placeholder collection.anki2; the real notes are in anki21(b).
        collection_name = next(
            (
                n
                for n in ("collection.anki21", "collection.anki21b", "collection.anki2")
                if n in names
            ),
            None,
        )
        if collection_name is None or collection_name.endswith("b"):
            raise ValueError("No supported Anki collection database found (anki21b is compressed)")
        db_path = out_dir / ".collection.sqlite"
        with archive.open(collection_name) as source, db_path.open("wb") as target:
            shutil.copyfileobj(source, target)
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
            # Keep only the final name component so archive entries cannot escape media_dir.
            safe = Path(original_name).name
            target = media_dir / safe
            if archive_name in names and safe not in ("", ".", "..") and not target.exists():
                with archive.open(archive_name) as source, target.open("wb") as stream:
                    shutil.copyfileobj(source, stream)

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
            }
        )
    paintings = enrich_collection_metadata(paintings)
    write_json(out_dir / "catalog.json", {"version": 1, "paintings": paintings})
    return paintings


def export_metadata(catalog_path: Path, output: Path) -> None:
    fields = ("id", "title", "artist", "year", "movement", "medium", "tags")
    paintings = [
        {key: p.get(key, "") for key in fields} for p in read_json(catalog_path)["paintings"]
    ]
    write_json(output, {"version": 1, "paintings": paintings})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_download = sub.add_parser("download", help="Fetch the latest shared .apkg from AnkiWeb")
    p_download.add_argument("--deck-id", type=int, default=DECK_ID)
    p_download.add_argument("--output", type=Path, default=DATA / "tableaux-de-maitres.apkg")
    p_extract = sub.add_parser("extract", help="Extract note fields and original deck images")
    p_extract.add_argument("--apkg", type=Path, default=DATA / "tableaux-de-maitres.apkg")
    p_extract.add_argument("--output", type=Path, default=DATA)
    p_metadata = sub.add_parser("metadata", help="Export all note metadata without image data")
    p_metadata.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    p_metadata.add_argument("--output", type=Path, default=ROOT / "catalog" / "paintings.json")
    args = parser.parse_args()
    if args.command == "download":
        print(download_deck(args.output, args.deck_id))
    elif args.command == "extract":
        print(f"Extracted {len(extract_apkg(args.apkg, args.output))} notes")
    elif args.command == "metadata":
        export_metadata(args.catalog, args.output)
        print(args.output)


if __name__ == "__main__":
    main()

"""Join a split Painting TV collection download, checking every part's checksum.

Usage: python join_pack.py painting-pack.parts.json --output painting-pack.zip
Uses only the standard library; memory use stays below a few megabytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CHUNK = 1024 * 1024


def split_pack(source: Path, directory: Path, *, part_size: int = 1_900_000_000) -> Path:
    if part_size <= 0:
        raise ValueError("Part size must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    full_hash = hashlib.sha256()
    parts = []
    with source.open("rb") as stream:
        while block := stream.read(min(CHUNK, part_size)):
            name = source.name + f".{len(parts) + 1:03}"
            digest = hashlib.sha256()
            size = 0
            with (directory / name).open("wb") as output:
                while block:
                    output.write(block)
                    digest.update(block)
                    full_hash.update(block)
                    size += len(block)
                    block = stream.read(min(CHUNK, part_size - size)) if size < part_size else b""
            parts.append({"name": name, "size": size, "sha256": digest.hexdigest()})
    manifest = directory / "painting-pack.parts.json"
    manifest.write_text(
        json.dumps(
            {
                "archiveName": source.name,
                "size": source.stat().st_size,
                "sha256": full_hash.hexdigest(),
                "parts": parts,
            },
            indent=2,
        )
        + "\n"
    )
    return manifest


def join_pack(manifest: Path, output: Path) -> None:
    value = json.loads(manifest.read_text())
    for part in value["parts"]:
        if (
            Path(part["name"]).name != part["name"]
            or not (manifest.parent / part["name"]).is_file()
        ):
            raise ValueError(f"Missing or unsafe part: {part['name']}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    full = hashlib.sha256()
    total = 0
    try:
        with temporary.open("wb") as stream:
            for part in value["parts"]:
                digest = hashlib.sha256()
                size = 0
                with (manifest.parent / part["name"]).open("rb") as source:
                    for block in iter(lambda: source.read(CHUNK), b""):
                        digest.update(block)
                        full.update(block)
                        size += len(block)
                        stream.write(block)
                if size != part["size"] or digest.hexdigest() != part["sha256"]:
                    raise ValueError(f"Incomplete or corrupt part: {part['name']}")
                total += size
        if total != value["size"] or full.hexdigest() != value["sha256"]:
            raise ValueError("Combined collection checksum does not match")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("painting-pack.zip"))
    args = parser.parse_args()
    join_pack(args.manifest.resolve(), args.output.resolve())
    print(f"Verified collection saved to {args.output}")


if __name__ == "__main__":
    main()

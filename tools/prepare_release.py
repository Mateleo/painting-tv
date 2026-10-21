"""Stage a versioned APK and its checksum from Android build metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare_release(apk_dir: Path, output: Path, tag: str) -> Path:
    metadata = json.loads((apk_dir / "output-metadata.json").read_text())
    (apk,) = metadata["elements"]
    version = apk["versionName"]
    if tag != f"v{version}":
        raise ValueError(f"Release tag {tag} does not match APK version v{version}")
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"painting-tv-{version}.apk"
    shutil.copyfile(apk_dir / apk["outputFile"], target)
    with target.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {target.name}\n")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v0.4.1")
    parser.add_argument("--apk-dir", type=Path, default=ROOT / "app/build/outputs/apk/release")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "data" / f"release-{args.tag}"
    print(prepare_release(args.apk_dir, output, args.tag))


if __name__ == "__main__":
    main()

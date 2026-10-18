import hashlib
import json
from pathlib import Path

import pytest

from tools.prepare_release import prepare_release


def build_metadata(directory: Path) -> None:
    (directory / "app-debug.apk").write_bytes(b"built APK")
    (directory / "output-metadata.json").write_text(
        json.dumps({"elements": [{"versionName": "0.4.1", "outputFile": "app-debug.apk"}]})
    )


def test_release_filename_and_checksum_include_built_version(tmp_path):
    build_metadata(tmp_path)
    output = tmp_path / "release"
    apk = prepare_release(tmp_path, output, "v0.4.1")
    assert apk.name == "painting-tv-0.4.1.apk"
    assert apk.read_bytes() == b"built APK"
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    assert (output / "SHA256SUMS.txt").read_text() == f"{digest}  {apk.name}\n"


def test_mismatched_release_tag_does_not_stage_an_apk(tmp_path):
    build_metadata(tmp_path)
    output = tmp_path / "release"
    with pytest.raises(ValueError, match="does not match"):
        prepare_release(tmp_path, output, "v0.4.2")
    assert not output.exists()

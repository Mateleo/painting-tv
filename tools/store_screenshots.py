"""Render the store's TV screenshots from tools/screenshots.html with headless Chromium.

The page loads painting images from the dataset export, so run tools.export_dataset first.
Writes 1920 x 1080 PNGs to fastlane/metadata/android/<language>/images/tvScreenshots/.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "tools/screenshots.html"
METADATA = ROOT / "fastlane/metadata/android"
LANGUAGES = {"en-US": "en", "fr-FR": "fr"}
SHOTS = 4


def render(browser: str, url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            browser,
            "--headless",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            "--force-device-scale-factor=2",
            "--window-size=960,540",
            "--virtual-time-budget=10000",
            f"--screenshot={target}",
            url,
        ],
        check=True,
        capture_output=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default=shutil.which("chromium") or "chromium")
    args = parser.parse_args()
    if not (ROOT / "data/hf-upload/images").is_dir():
        raise SystemExit("Missing data/hf-upload/images: run python -m tools.export_dataset first")
    for folder, lang in LANGUAGES.items():
        for shot in range(1, SHOTS + 1):
            target = METADATA / folder / "images/tvScreenshots" / f"{shot}.png"
            render(args.browser, f"{PAGE.as_uri()}?shot={shot}&lang={lang}", target)
            print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()

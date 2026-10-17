"""Search Commons for larger reproductions and verify them against every deck image.

This pass runs sequentially, saves every lookup, and stops on rate limiting.
It records exact image-comparison metrics; matches are automatic, not human reviews.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from tools.common import read_json, state_records, write_json
from tools.painting_catalog import strip_html
from tools.source_upgrades import visual_match

ROOT = Path(__file__).resolve().parents[1]
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "PaintingTV/0.2 (https://github.com/Mateleo/painting-tv; personal art collection)"


class RateLimited(Exception):
    pass


class Client:
    def __init__(self, delay: float = 1.0):
        self.delay = max(0.2, delay)
        self.last = 0.0

    def get(self, url: str, maximum: int = 4_000_000) -> bytes:
        pause = self.delay - (time.monotonic() - self.last)
        if pause > 0:
            time.sleep(pause)
        self.last = time.monotonic()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if int(response.headers.get("Content-Length", "0")) > maximum:
                    raise ValueError("Image exceeds configured download limit")
                result = response.read(maximum + 1)
        except urllib.error.HTTPError as error:
            if error.code in (429, 403):
                raise RateLimited(
                    f"HTTP {error.code}; Retry-After: {error.headers.get('Retry-After', 'unspecified')}"
                ) from error
            raise
        if len(result) > maximum:
            raise ValueError("Image exceeds configured download limit")
        return result

    def query(self, **params: Any) -> dict[str, Any]:
        query = {"action": "query", "format": "json", "prop": "imageinfo", **params}
        payload = json.loads(self.get(API + "?" + urllib.parse.urlencode(query)))
        if "error" in payload:
            raise ValueError(str(payload["error"]))
        return payload.get("query", {}).get("pages", {})

    def file_info(self, title: str, **params: Any) -> dict[str, Any]:
        page = next(iter(self.query(titles=title, **params).values()), {})
        return (page.get("imageinfo") or [{}])[0]

    def candidates(self, painting: dict[str, Any]) -> list[dict[str, Any]]:
        title = painting.get("title", "").replace('"', " ")
        artist = painting.get("artist", "").replace('"', " ")
        pages = self.query(
            generator="search",
            gsrsearch=(title[:180] + " " + artist + " filetype:bitmap").strip(),
            gsrnamespace=6,
            gsrlimit=5,
            iiprop="url|size|mime|extmetadata",
            iiurlwidth=480,
        )
        rows = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
                continue
            rows.append(
                {
                    "fileTitle": page.get("title", ""),
                    "imageUrl": info.get("url", ""),
                    "thumbnailUrl": info.get("thumburl", info.get("url", "")),
                    "width": info.get("width", 0),
                    "height": info.get("height", 0),
                    "bytes": info.get("size", 0),
                    "sourceUrl": info.get("descriptionurl", ""),
                    **license_fields(info),
                }
            )
        return sorted(rows, key=lambda row: row["width"] * row["height"], reverse=True)

    def display_derivative(self, candidate: dict[str, Any]) -> str:
        # Some museum scans are hundreds of MB. Request a documented Commons
        # thumbnail derivative with enough pixels for a 4K TV instead of fetching
        # the entire scan into this machine's memory.
        width = min(
            candidate["width"],
            5000,
            max(1, int((32_000_000 * candidate["width"] / candidate["height"]) ** 0.5)),
        )
        info = self.file_info(candidate["fileTitle"], iiprop="url|size", iiurlwidth=width)
        if "thumburl" not in info:
            raise ValueError("No large display derivative available")
        candidate["downloadIsDerivative"] = True
        candidate["downloadWidth"] = info.get("thumbwidth")
        candidate["downloadHeight"] = info.get("thumbheight")
        return info["thumburl"]


def license_fields(info: dict[str, Any]) -> dict[str, str]:
    meta = info.get("extmetadata", {})

    def value(key: str) -> str:
        return meta.get(key, {}).get("value", "")

    return {
        "license": strip_html(value("LicenseShortName")),
        "licenseUrl": value("LicenseUrl"),
        "attribution": strip_html(value("Artist")),
        "credit": strip_html(value("Credit")),
    }


def run(
    catalog_path: Path, output: Path, *, delay: float = 1.0, limit: int | None = None
) -> dict[str, Any]:
    catalog_path = catalog_path.resolve()
    paintings = read_json(catalog_path)["paintings"]
    path = output / "state.json"
    state = state_records(path)
    client = Client(delay)
    count = 0
    for painting in paintings:
        identity = painting["id"]
        if identity in state and state[identity].get("status") not in (
            "lookup-error",
            "rate-limited",
        ):
            continue
        if limit is not None and count >= limit:
            break
        count += 1
        result: dict[str, Any] = {"id": identity, "status": "no-verified-upgrade", "candidates": []}
        reference = catalog_path.parent / painting.get(
            "originalImageUrl", painting.get("imageUrl", "")
        )
        try:
            candidates = client.candidates(painting)
            result["candidates"] = candidates
            if not reference.is_file():
                result["status"] = "needs-review-no-reference"
            else:
                with Image.open(reference) as image:
                    reference_area = image.width * image.height
                for candidate in candidates:
                    if candidate["width"] * candidate["height"] <= reference_area * 1.2:
                        continue
                    try:
                        thumbnail = client.get(candidate["thumbnailUrl"], maximum=4_000_000)
                        comparison = visual_match(
                            reference, thumbnail, max_rmse=28.0, max_hash_distance=12
                        )
                        candidate["visualMatch"] = comparison
                        if not comparison["match"]:
                            continue
                        large = (
                            candidate.get("bytes", 0) > 64_000_000
                            or candidate["width"] * candidate["height"] > 32_000_000
                        )
                        download_url = (
                            client.display_derivative(candidate) if large else candidate["imageUrl"]
                        )
                        candidate["downloadUrl"] = download_url
                        raw = client.get(download_url, maximum=64_000_000)
                        final_comparison = visual_match(
                            reference, raw, max_rmse=28.0, max_hash_distance=12
                        )
                        if not final_comparison["match"]:
                            candidate["originalVisualMismatch"] = final_comparison
                            continue
                        with Image.open(io.BytesIO(raw)) as image:
                            image.load()
                            fmt, width, height = image.format, image.width, image.height
                        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(fmt)
                        if suffix is None:
                            continue
                        master = output.parent / "commons-masters" / (identity + suffix)
                        master.parent.mkdir(parents=True, exist_ok=True)
                        temporary = master.with_suffix(suffix + ".partial")
                        temporary.write_bytes(raw)
                        temporary.replace(master)
                        result.update(
                            status="accepted",
                            selected=candidate,
                            candidate_dimensions=[width, height],
                            master_path=str(master.resolve()),
                            sha256=hashlib.sha256(raw).hexdigest(),
                            visual_match=final_comparison,
                        )
                        break
                    except RateLimited:
                        raise
                    except (OSError, ValueError) as error:
                        candidate["error"] = str(error)
        except RateLimited as error:
            result.update(status="rate-limited", reason=str(error))
            state[identity] = result
            write_json(path, {"records": state}, compact=True)
            print(
                f"Commons paused: {error}. Saved {len(state)}/{len(paintings)}; resume later.",
                flush=True,
            )
            break
        except (OSError, ValueError, KeyError) as error:
            result.update(status="lookup-error", reason=str(error))
        state[identity] = result
        write_json(path, {"records": state}, compact=True)
        if len(state) % 10 == 0:
            print(
                f"Commons {len(state)}/{len(paintings)}; accepted={sum(r.get('status') == 'accepted' for r in state.values())}",
                flush=True,
            )
    report = {
        "records": len(state),
        "total": len(paintings),
        "accepted": sum(r.get("status") == "accepted" for r in state.values()),
        "rateLimited": any(r.get("status") == "rate-limited" for r in state.values()),
    }
    print(json.dumps(report), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/commons-upgrades")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run(args.catalog, args.output, delay=args.delay, limit=args.limit)


if __name__ == "__main__":
    main()

"""Find and validate higher-resolution WikiArt sources for the local catalog.

Run from the repository root with ``python -m tools.source_upgrades``. Requests
are paced, at most two are in flight, and image decoding is serialized. The
state file is updated after every record so interrupted runs can resume.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import functools
import hashlib
import html
import io
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

from tools.common import read_json, state_records, write_json

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "PaintingTV/0.2 (https://github.com/Mateleo/painting-tv)"
MIN_INTERVAL = 0.2
MAX_IMAGE_BYTES = 64 * 1024 * 1024
_request_lock = threading.Lock()
_decode_lock = threading.Lock()
_blocked = threading.Event()
_last_request = 0.0

# Deck titles are localized while WikiArt uses their canonical English slugs.
CANONICAL_OVERRIDES = {
    "leonard-de-vinci_la-joconde-1504.jpg": ("leonardo-da-vinci", "mona-lisa"),
    "vincent-van-gogh_la-nuit-etoilee-1889.jpg": ("vincent-van-gogh", "the-starry-night-1889"),
    "sandro-botticelli_la-naissance-de-venus-1485.jpg": (
        "sandro-botticelli",
        "the-birth-of-venus-1485",
    ),
    "claude-monet_impression-soleil-levant-1873.jpg": ("claude-monet", "impression-sunrise"),
    "henri-de-toulouse-lautrec_dans-le-lit-le-baiser-1892.jpg": (
        "henri-de-toulouse-lautrec",
        "in-bed-the-kiss-1892",
    ),
    "alfons-mucha_zodiac-1896.jpg": ("alphonse-mucha", "zodiac-1896"),
    "alfons-mucha_poster-for-victorien-sardou-s-gismonda-starring-sarah-bernhardt-at-the-théâtre-de-la-1894.jpg": (
        "alphonse-mucha",
        "poster-for-victorien-sardou-s-gismonda-starring-sarah-bernhardt-at-the-théâtre-de-la-1894",
    ),
    "georges-seurat_la-tour-eiffel-1889.jpg": ("georges-seurat", "the-eiffel-tower-1889"),
    "claude-monet_femmes-au-jardin-1866.jpg": ("claude-monet", "women-in-the-garden-1866"),
    "gustav-klimt_le-baiser-1908.jpg": ("gustav-klimt", "the-kiss-1908"),
    "raphael_lecole-dathenes-1511.jpg": (
        "raphael",
        "school-of-athens-detail-from-right-hand-side-showing-diogenes-on-the-steps-and-euclid-1511",
    ),
}
ARTIST_ALIASES = {"alfons-mucha": ("alphonse-mucha",)}


def _page_url(artist: str, title: str) -> str:
    quote = urllib.parse.quote
    return f"https://www.wikiart.org/en/{quote(artist, safe='-')}/{quote(title, safe='-')}"


def source_page_for(path: str | Path) -> str:
    return source_page_candidates(path)[0]


def source_page_candidates(path: str | Path) -> list[str]:
    filename = Path(path).name
    if filename in CANONICAL_OVERRIDES:
        return [_page_url(*CANONICAL_OVERRIDES[filename])]
    stem = Path(filename).stem
    if "_" not in stem:
        raise ValueError(f"Cannot derive artist/title slugs from {filename}")
    artist, title = stem.split("_", 1)
    yearless = re.sub(r"-\d{3,4}(?:-\d+)?$", "", title)
    titles = [title] if yearless == title else [title, yearless]
    # Exact-year slug first; known WikiArt artist-name variants follow each title.
    artists = [artist, *ARTIST_ALIASES.get(artist, ())]
    return [_page_url(a, t) for t in titles for a in artists]


def extract_image_url(page: bytes | str) -> str | None:
    text = page.decode("utf-8", "replace") if isinstance(page, bytes) else page
    # og:image is the canonical high-resolution display URL. Strip only the
    # public size suffix (!Large.jpg), retaining revision markers such as (1).
    match = re.search(
        r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)', text, re.I
    ) or re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', text, re.I)
    if not match:
        return None
    return re.sub(
        r"!(?:Large|Medium|Small|[0-9]+)\.jpg(?=$|\?)",
        "",
        html.unescape(match.group(1)),
        flags=re.I,
    )


def encode_url(url: str) -> str:
    """Percent-encode Unicode in a URL while keeping existing escapes."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
            urllib.parse.quote(parts.query, safe="=&%/:@!$'()*+,;-._~?"),
            urllib.parse.quote(parts.fragment, safe="%:@/?"),
        )
    )


def _request(url: str, *, max_bytes: int = 2_000_000, timeout: int = 20) -> bytes:
    global _last_request
    with _request_lock:
        if _blocked.is_set():
            raise RuntimeError("WikiArt host paused after access was blocked")
        delay = MIN_INTERVAL - (time.monotonic() - _last_request)
        if delay > 0:
            time.sleep(delay)
        _last_request = time.monotonic()
    request = urllib.request.Request(
        encode_url(url),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,image/avif,image/webp,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            _blocked.set()
            retry_after = exc.headers.get("Retry-After", "")
            raise RuntimeError(
                f"WikiArt blocked access (HTTP {exc.code}; Retry-After={retry_after})"
            ) from exc
        raise
    if len(data) > max_bytes:
        raise ValueError(f"Response exceeds {max_bytes} bytes")
    return data


class OversizedImage(ValueError):
    pass


def check_image(data: bytes) -> tuple[tuple[int, int], str | None]:
    """Verify, then decode (bounded JPEG draft) downloaded image bytes; return size and format."""
    with _decode_lock:
        with Image.open(io.BytesIO(data)) as image:
            size, fmt = image.size, image.format
            image.verify()
        if fmt != "JPEG" and size[0] * size[1] > 32_000_000:
            raise OversizedImage("non-JPEG candidate exceeds the 32-megapixel decode limit")
        with Image.open(io.BytesIO(data)) as image:
            if fmt == "JPEG":
                image.draft("RGB", (4096, 4096))
            image.load()
    return size, fmt


def visual_match(
    reference: Path,
    candidate: bytes,
    *,
    max_aspect_delta: float = 0.02,
    max_rmse: float = 36.0,
    max_hash_distance: int = 18,
) -> dict[str, Any]:
    """Compare normalized thumbnails; results are cues, never art judgment."""
    with _decode_lock:
        ref_size, ref_thumb = _reference_thumb(reference, reference.stat().st_mtime_ns)
        with Image.open(io.BytesIO(candidate)) as cand:
            cand_size = cand.size
            cand.draft("RGB", (512, 512))
            cand.load()
            cand_thumb = _normalized_thumb(cand)
        rmse = sum(ImageStat.Stat(ImageChops.difference(ref_thumb, cand_thumb)).rms) / 3
        distance = (_dhash(ref_thumb) ^ _dhash(cand_thumb)).bit_count()
    ref_aspect = ref_size[0] / ref_size[1]
    aspect_delta = abs(ref_aspect - cand_size[0] / cand_size[1]) / ref_aspect
    return {
        "reference_dimensions": list(ref_size),
        "candidate_dimensions": list(cand_size),
        "aspect_delta_fraction": round(aspect_delta, 5),
        "thumbnail_rgb_rmse": round(rmse, 3),
        "dhash_distance": distance,
        "match": aspect_delta <= max_aspect_delta
        and rmse <= max_rmse
        and distance <= max_hash_distance,
    }


@functools.lru_cache(maxsize=8)
def _reference_thumb(path: Path, _mtime_ns: int) -> tuple[tuple[int, int], Image.Image]:
    """Decode a reference once per comparison batch (Commons checks up to ten candidates)."""
    with Image.open(path) as ref:
        ref.load()
        return ref.size, _normalized_thumb(ref)


def letterbox(image: Image.Image, size: tuple[int, int], fill: str) -> Image.Image:
    """Fit ``image`` inside ``size`` without enlarging it, centred on a solid canvas."""
    image = image.convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, fill)
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def _normalized_thumb(image: Image.Image) -> Image.Image:
    return letterbox(image, (96, 96), "#202020")


def _dhash(image: Image.Image) -> int:
    values = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes()
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (values[y * 9 + x] > values[y * 9 + x + 1])
    return bits


def _candidate_for(
    painting: dict[str, Any], catalog_root: Path
) -> tuple[list[str], Path | None, str]:
    image = painting.get("imageUrl") or painting.get("originalImageUrl") or ""
    ref = (
        (catalog_root / image).resolve()
        if image and not image.startswith(("http://", "https://"))
        else None
    )
    try:
        pages = (
            source_page_candidates(image)
            if image
            else [_page_url(slug(painting.get("artist", "")), slug(painting.get("title", "")))]
        )
    except ValueError as error:
        return [], ref, str(error)
    return pages, ref, ""


def slug(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def process_record(
    painting: dict[str, Any], catalog_root: Path, masters_dir: Path
) -> dict[str, Any]:
    item_id = str(painting.get("id", ""))
    pages, reference, error = _candidate_for(painting, catalog_root)
    result: dict[str, Any] = {
        "id": item_id,
        "source_page_url": "",
        "source_page_candidates": pages,
        "status": "needs-review",
        "reason": "",
    }
    if error or not pages:
        result["reason"] = error or "no-source-page-slug"
        return result
    if reference is not None and not reference.is_file():
        reference = None
    try:
        image_url = None
        page_url = ""
        not_found = []
        no_image = []
        for candidate_page in pages:
            try:
                page = _request(candidate_page)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    not_found.append(candidate_page)
                    continue
                raise
            page_url = candidate_page
            image_url = extract_image_url(page)
            if image_url:
                break
            no_image.append(candidate_page)
        result["tried_not_found"] = not_found
        result["tried_without_image"] = no_image
        if not image_url:
            result.update(
                status="no-candidate",
                reason="all WikiArt page slugs returned 404 or had no og:image",
            )
            return result
        result["source_page_url"] = page_url
        result["http_page_status"] = "ok"
        result["source_image_url"] = image_url
        if reference is None:
            result.update(reason="candidate-found-but-no-local-reference-for-visual-verification")
            return result
        candidate = _request(image_url, max_bytes=MAX_IMAGE_BYTES, timeout=35)
        result["candidate_bytes"] = len(candidate)
        result["candidate_sha256"] = hashlib.sha256(candidate).hexdigest()
        try:
            candidate_size, fmt = check_image(candidate)
        except OversizedImage as oversized:
            result.update(status="needs-review", reason=str(oversized))
            return result
        comparison = visual_match(reference, candidate)
        ref_size = comparison["reference_dimensions"]
        result.update(
            reference_dimensions=ref_size,
            candidate_dimensions=list(candidate_size),
            candidate_format=fmt,
            visual_match=comparison,
        )
        if not comparison["match"]:
            result.update(
                status="rejected-visual-mismatch",
                reason="candidate did not pass aspect/RMSE/dHash checks",
            )
            return result
        if candidate_size[0] <= ref_size[0] and candidate_size[1] <= ref_size[1]:
            result.update(
                status="candidate-not-higher-resolution",
                reason="candidate dimensions do not exceed local reference",
            )
            return result
        if fmt not in ("JPEG", "PNG"):
            result.update(
                status="needs-review",
                reason=f"candidate format {fmt} is unsupported for source master promotion",
            )
            return result
        masters_dir.mkdir(parents=True, exist_ok=True)
        target = masters_dir / f"{item_id}.jpg"
        temp = target.with_suffix(".jpg.partial")
        temp.write_bytes(candidate)
        os.replace(temp, target)
        result.update(
            status="accepted",
            reason="higher-resolution candidate passed visual checks",
            master_path=f"../masters/{item_id}.jpg",
        )
        return result
    except urllib.error.HTTPError as error:
        result.update(
            status="source-page-error" if error.code != 404 else "no-candidate",
            http_status=error.code,
            reason=str(error),
        )
    except Exception as error:
        result.update(
            status="blocked" if _blocked.is_set() else "source-error",
            reason=f"{type(error).__name__}: {error}",
        )
    return result


def _save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    write_json(path, {"schema_version": 1, "records": state}, compact=True)


def _needs_attempt(previous: dict[str, Any] | None, retry_no_candidate: bool) -> bool:
    if previous is None:
        return True
    status = previous.get("status")
    return (
        status in ("source-error", "source-page-error", "blocked", "not-attempted-host-blocked")
        or (
            status == "no-candidate"
            and (retry_no_candidate or "source_page_candidates" not in previous)
        )
        or (status == "needs-review" and "candidate is PNG" in previous.get("reason", ""))
    )


def run_pass(
    catalog_path: Path,
    output_dir: Path,
    *,
    workers: int = 2,
    resume: bool = True,
    retry_no_candidate: bool = False,
) -> dict[str, Any]:
    if not 1 <= workers <= 2:
        raise ValueError("workers must be 1 or 2")
    catalog_path = catalog_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    masters = output_dir.parent / "masters"
    state_path = output_dir / "state.json"
    state = state_records(state_path) if resume else {}
    paintings = read_json(catalog_path).get("paintings", [])
    pending = [
        p for p in paintings if _needs_attempt(state.get(str(p.get("id", ""))), retry_no_candidate)
    ]
    done = len(paintings) - len(pending)
    print(
        f"Source pass: {done}/{len(paintings)} already recorded; {len(pending)} pending; workers={workers}",
        flush=True,
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_record, p, catalog_path.parent, masters): str(p.get("id", ""))
            for p in pending
        }
        for future in concurrent.futures.as_completed(futures):
            if future.cancelled():
                continue
            record_id = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {
                    "id": record_id,
                    "status": "source-error",
                    "reason": f"{type(error).__name__}: {error}",
                }
            # Results still in flight after a block are saved too, so no finished download is lost.
            state[record_id] = result
            _save_state(state_path, state)
            done += 1
            if done % 25 == 0 or done == len(paintings) or _blocked.is_set():
                print(
                    f"Source pass progress: {done}/{len(paintings)}; accepted={sum(x.get('status') == 'accepted' for x in state.values())}; blocked={_blocked.is_set()}",
                    flush=True,
                )
            if _blocked.is_set():
                for other in futures:
                    other.cancel()
    # Mark unstarted records explicitly when access has been blocked.
    if _blocked.is_set():
        for painting in paintings:
            record_id = str(painting.get("id", ""))
            state.setdefault(
                record_id,
                {
                    "id": record_id,
                    "status": "not-attempted-host-blocked",
                    "reason": "host denied requests; rerun after access is available",
                },
            )
        _save_state(state_path, state)
    output_paintings = []
    for painting in paintings:
        p = dict(painting)
        image = p.get("imageUrl") or p.get("originalImageUrl") or ""
        if image and not image.startswith(("http://", "https://")):
            p["imageUrl"] = (
                f"../{image.removeprefix('data/')}" if image.startswith("data/") else f"../{image}"
            )
        result = state.get(str(p.get("id", "")), {})
        p["sourceUpgradeStatus"] = result.get("status", "not-attempted")
        p["sourcePageUrl"] = result.get("source_page_url", "")
        p["sourceImageUrl"] = result.get("source_image_url", "")
        if result.get("status") == "accepted":
            p["upgradedImageUrl"] = result["master_path"]
            p["upgradedWidth"], p["upgradedHeight"] = result["candidate_dimensions"]
        output_paintings.append(p)
    write_json(output_dir / "catalog.json", {"version": 1, "paintings": output_paintings})
    counts = collections.Counter(result.get("status", "unknown") for result in state.values())
    rows = []
    for painting in paintings:
        result = state.get(str(painting.get("id", "")), {})
        rows.append(
            {
                "title": painting.get("title", ""),
                "artist": painting.get("artist", ""),
                **{
                    key: result.get(key)
                    for key in (
                        "id",
                        "status",
                        "reason",
                        "source_page_url",
                        "source_page_candidates",
                        "source_image_url",
                        "reference_dimensions",
                        "candidate_dimensions",
                        "candidate_format",
                        "candidate_bytes",
                        "candidate_sha256",
                        "visual_match",
                        "master_path",
                        "tried_not_found",
                        "tried_without_image",
                        "http_status",
                    )
                    if key in result
                },
            }
        )
    summary = {
        "schema_version": 1,
        "record_count": len(paintings),
        "state_record_count": len(state),
        "status_counts": dict(counts),
        "attempted_count": sum(n for k, n in counts.items() if not k.startswith("not-attempted")),
        "accepted_count": counts.get("accepted", 0),
        "source_host_blocked": _blocked.is_set(),
        "method": {
            "source": "WikiArt regular HTML page og:image; public size suffix removed to request the original image URL",
            "verification": "full decode verification followed by bounded JPEG draft decode; candidate thumbnail compared against local reference",
            "visual_thresholds": {
                "relative_aspect_difference_max": 0.02,
                "thumbnail_rgb_rmse_max": 36.0,
                "dhash_distance_max": 18,
            },
            "decision_note": "Accepted means the candidate passed automated source and image-match checks; it is not manual verification or an art-quality judgment. Mismatches and absent references remain unpromoted.",
            "license_note": "WikiArt page URLs are retained as provenance. Page HTML does not provide a reliable per-image license field in the metadata used by this pass.",
        },
        "records": rows,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/upgrades")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--retry-no-candidate",
        action="store_true",
        help="Retry only records previously marked no-candidate",
    )
    parser.add_argument("--report", type=Path, default=ROOT / "catalog/source-upgrades.json")
    args = parser.parse_args(argv)
    summary = run_pass(
        args.catalog,
        args.output_dir,
        workers=args.workers,
        resume=not args.no_resume,
        retry_no_candidate=args.retry_no_candidate,
    )
    write_json(args.report, summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if not summary["source_host_blocked"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

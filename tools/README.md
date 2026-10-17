# Painting catalog tools

These tools fetch the shared Anki deck, extract the note fields and embedded
images, suggest Wikimedia Commons matches with image dimensions and license
metadata, and package manually approved images for offline display. The
resolver stores candidates and provenance in data/catalog.json; a similarity
score is a review aid, never proof of identity.

Python 3.10 or newer is required. The original extraction/resolver commands use
only the standard library; the full quality workflow below also uses Pillow.
From the repository root:

    python3 -m tools.painting_catalog download
    python3 -m tools.painting_catalog extract
    python3 -m tools.painting_catalog manifest
    python3 -m tools.painting_catalog metadata

The confirmed shared deck is https://ankiweb.net/shared/info/171273480.
The download command requests the current deck download key from AnkiWeb and
writes data/tableaux-de-maitres.apkg. The extract command creates
data/catalog.json and copies original images to data/images/. The package is
a ZIP containing an SQLite collection, media-name map, and image entries.

To search Commons for possible matches, begin with a small batch:

    python3 -m tools.painting_catalog resolve --limit 20

Commons is queried one item at a time with a one-second default delay. Each
candidate records its source page, direct image URL, dimensions, license
label, and title/artist token-overlap score. Results remain in a resumable
needs-review state and never replace the embedded image automatically.
Requests honor Retry-After and use bounded backoff after HTTP 429. Approve a
candidate after checking it:

    python3 -m tools.painting_catalog approve d459320dbad84895 --candidate 0

The manifest command exports the app contract (version and paintings). By
default it uses relative paths to embedded or downloaded images. Add --online
to use approved HTTPS source URLs while unresolved records retain their local
images. Once candidates are approved, pack downloads them, skips existing
files, and records resumable local paths for the app bundle:

    python3 -m tools.painting_catalog pack --min-width 3840
    python3 -m tools.painting_catalog bundle

The pack command does not fetch unresolved or merely suggested results.
Original scans vary in resolution and orientation; min-width filters by source
width but cannot ensure a vertical work fills a 4K screen.

The bundle command writes data/painting-pack.zip. It contains catalog.json at
the ZIP root and an images/ directory with embedded deck images.
Approved high-resolution downloads are included alongside them, and the
packaged catalog points to those approved files. The bundle stays usable
offline even for paintings that have not yet been matched. Four deck notes
have no embedded image and are omitted from the app bundle; bundle-report.json
inside the ZIP and the adjacent report JSON list those omitted records.

The metadata command exports all 2,160 notes, without images or resolver
details, to catalog/paintings.json. This compact catalog can be checked into
the repository while the source deck and image assets stay under ignored data/.

Run the unit tests with:

    .venv/bin/python -m unittest discover -s tests

## Audit and improve the complete collection

Install the optional imaging dependency in a virtual environment:

    uv venv
    uv pip install -e '.[images]'

Then run the sequential audit and resumable source passes:

    .venv/bin/python -m tools.image_quality --no-starters
    .venv/bin/python -m tools.source_upgrades
    .venv/bin/python -m tools.commons_upgrades --delay 1
    .venv/bin/python -m tools.curated_sources
    .venv/bin/python -m tools.review_mismatches --apply-decisions catalog/reviewed-source-overrides.json
    .venv/bin/python -m tools.build_quality_pack
    .venv/bin/python -m tools.quality_review

`source_upgrades` checks WikiArt page routes derived from every original image
filename, preserving year-bearing titles and public CDN revision names. It
uses two paced network workers and one image decoder. The Commons pass checks
candidate thumbnails before downloading a larger file and stops on access or
rate-limit responses. A larger display derivative is requested for exceptionally
large Commons scans to avoid loading hundreds of megabytes into RAM. Source
responses, failed lookups, dimensions, checksums and comparison metrics are saved
under `data/upgrades/` and `data/commons-upgrades/`. A completed WikiArt pass is
summarized in `catalog/source-upgrades.json` with every attempted record.

Pixel/aspect/hash comparisons are automatic verification aids, not human
approval or proof that a larger scan contains real additional detail. Known
missing images use the explicitly cited `catalog/source-overrides.json` entries;
their title/artist/date evidence is recorded separately from pixel matching.
Strict visual mismatches can be inspected in paired contact sheets with
`tools.review_mismatches`. Model-reviewed exceptions are kept separately in
`catalog/reviewed-source-overrides.json` and `data/review-upgrades/state.json`;
the merger only selects entries explicitly marked accepted. They retain their
review reason and must not be described as human approval.
Run the review module without `--apply-decisions` to prepare paired contact
sheets for a new review. Replaying saved decisions checks both the recorded
candidate checksum and the bytes on disk before promotion.

`build_quality_pack` merges the available sources, chooses the strongest
screen-fill resolution among verified candidates, keeps an original fallback,
and produces `data/tv-quality-pack.zip`. It fully audits the selected exports
and records every original note in `catalog/quality-upgrade-report.json` and CSV.
`quality_review` generates the searchable, self-contained HTML review.

The encoder preserves source dimensions by default. It copies already compact
JPEGs unchanged, tries high-quality WebP where useful, and keeps the original
unless the candidate saves at least 5% and passes a 43 dB PSNR guard measured
on five full-resolution detail patches. PNGs can use exact lossless WebP.
This sampled guard limits recompression error; it is not a whole-image
perceptual guarantee. Original source masters stay unchanged in `data/masters/`
and `data/commons-masters/`. No image is AI-upscaled or enlarged.

For an explicitly smaller export, run the encoder separately:

    .venv/bin/python -m tools.optimize_images --catalog data/selected/catalog.json --max-edge 7680 --max-pixels 16600000

The app decodes JPEG, PNG and WebP. WebP works across its Android version range;
AVIF is not selected by default because the TV's Android version is unknown.
After a source pass is interrupted, rerun the same command to resume its saved
progress, then rebuild the pack. The release report states the actual source
coverage; incomplete network lookups must not be counted as checked replacements.

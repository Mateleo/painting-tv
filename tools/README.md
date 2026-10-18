# Painting catalog tools

These tools fetch the shared Anki deck, extract the note fields and embedded
images, find larger matching reproductions, and export the Hugging Face dataset
the app downloads.

Python 3.15 is pinned in `.python-version` and installed automatically by uv.
The deck commands use only the standard library; the quality workflow below
also uses Pillow. From the repository root:

    uv run --locked painting-catalog download
    uv run --locked painting-catalog extract
    uv run --locked painting-catalog metadata

The confirmed shared deck is https://ankiweb.net/shared/info/171273480.
The download command requests the current deck download key from AnkiWeb and
writes data/tableaux-de-maitres.apkg. The extract command creates
data/catalog.json and copies original images to data/images/. The package is
a ZIP containing an SQLite collection, media-name map, and image entries.

The metadata command exports all 2,160 notes, without images, to
catalog/paintings.json. This compact catalog is checked into the repository
while the source deck and image assets stay under ignored data/.

Run the unit tests with:

    uv run --locked --extra images pytest

## Audit and improve the complete collection

Install the optional imaging dependency in a virtual environment:

    uv sync --locked --extra images

Then run the sequential audit and resumable source passes:

    uv run --locked --extra images python -m tools.image_quality --no-starters
    uv run --locked --extra images python -m tools.source_upgrades
    uv run --locked --extra images python -m tools.commons_upgrades --delay 1
    uv run --locked --extra images python -m tools.curated_sources
    uv run --locked --extra images python -m tools.review_mismatches --apply-decisions catalog/reviewed-source-overrides.json
    uv run --locked --extra images python -m tools.build_quality_pack
    uv run --locked --extra images python -m tools.quality_review

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

Researched sources (Wikidata, museum open-access APIs, artist sites) come from
a separate manual research pass whose scripts are not part of this package.
Its decisions, accepted and rejected, are committed in
`catalog/research-sources.json`. Each record keeps its source page, licence,
checksum, and pairwise review verdict. `build_quality_pack` reads it by default;
the masters it points to stay in the ignored `data/research-masters/`.
A missing master is skipped; re-download it from its recorded `downloadUrl` and
compare the recorded `sha256`.

`build_quality_pack` merges the available sources, chooses the strongest
screen-fill resolution among verified candidates, keeps an original fallback,
and produces a dataset folder at `data/tv-quality-pack/` containing `catalog.json`
and its referenced images. It fully audits the selected exports
and records every original note in `catalog/quality-upgrade-report.json` and CSV.
`quality_review` generates the searchable, self-contained HTML review.

Two small committed maps feed every export, keyed by painting ID:
`catalog/titles-fr.json` gives the French title where the deck has an English
one, and `catalog/collections.json` gives the holding collection label. A
painting missing from the label map has no collection. The holdings research
that produces the label map is internal and kept out of the repository and the
dataset, under the ignored `.research/collections/`; it writes only
`catalog/collections.json` here.

The app's built-in **Download full collection** reads
`https://huggingface.co/datasets/Mateleo/painting-collection`. Export the
quality pack as that dataset, then upload it:

    uv run --locked --extra images python -m tools.export_dataset
    hf upload Mateleo/painting-collection data/hf-upload . --repo-type dataset --delete "*"

The export rebuilds `data/hf-upload/` with:

- `catalog.json`: the app contract, version 2. Only the fields the app reads,
  French titles applied, compact.
- `images/`: hard links to the pack images the catalog references; stale files
  are removed.
- `metadata.jsonl`: one row per image (`file_name`, display fields, source,
  licence, credit, bytes, SHA-256) for the Hub dataset viewer.
- `README.md`: the dataset card from `tools/dataset-card.md`, whose `configs`
  block points the viewer at `metadata.jsonl` and `images/`.

`--delete "*"` removes remote files the new export no longer has. Downloading
again on a TV that already has this collection fetches every image again into a
separate stage; resuming reuses images only within an unfinished download.

The encoder preserves source dimensions by default. It copies already compact
JPEGs unchanged, tries high-quality WebP where useful, and keeps the original
unless the candidate saves at least 5% and passes a 43 dB PSNR guard measured
on five full-resolution detail patches. PNGs can use exact lossless WebP.
This sampled guard limits recompression error; it is not a whole-image
perceptual guarantee. Original source masters stay unchanged in `data/masters/`
and `data/commons-masters/`. No image is AI-upscaled or enlarged.

For an explicitly smaller export, run the encoder separately:

    uv run --locked --extra images python -m tools.optimize_images --catalog data/selected/catalog.json --max-edge 7680 --max-pixels 16600000

The app decodes JPEG, PNG and WebP. WebP works across its Android version range;
AVIF is not selected by default because the TV's Android version is unknown.
After a source pass is interrupted, rerun the same command to resume its saved
progress, then rebuild the pack. The release report states the actual source
coverage; incomplete network lookups must not be counted as checked replacements.

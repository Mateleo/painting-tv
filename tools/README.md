# Painting catalog tools

These tools fetch the shared Anki deck, extract the note fields and embedded
images, suggest Wikimedia Commons matches with image dimensions and license
metadata, and package manually approved images for offline display. The
resolver stores candidates and provenance in data/catalog.json; a similarity
score is a review aid, never proof of identity.

Python 3.10 or newer is required. The tools use only the standard library.
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

    python3 -m unittest discover -s tests

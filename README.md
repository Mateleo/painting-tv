# Painting TV

A quiet, offline painting slideshow for Android TV and Google TV. Built with
Kotlin and Compose for TV; Python prepares the artwork collection. No account,
analytics, subscription, or server is needed for playback.

## Use it on your TV

Download `painting-tv.apk` and `painting-pack.zip` from the private repository's
[releases](https://github.com/Mateleo/painting-tv/releases). Install the APK on
your TV using your preferred Android TV installer, or use ADB below. The APK
starts with two public-domain paintings from The Metropolitan Museum of Art.

If a large collection is supplied as `painting-pack.zip.001`, `.002`, etc.,
download every part plus `painting-pack.parts.json` and `join-pack.py` into one
folder. Join and verify them on your computer before importing on the TV:

```sh
python join-pack.py painting-pack.parts.json --output painting-pack.zip
```

The join streams files and verifies their SHA-256 checksums. Do not import the
individual parts on the TV. GitHub's per-file release limit is why large packs
are split; splitting does not recompress or reduce image quality.

Open **Settings → Import collection ZIP** and choose `painting-pack.zip` from
USB or local storage. Keep the app open until the import starts. It continues
in a background task and reports progress. Allow notifications if prompted so
you can see that task. The gallery switches to the imported collection only
after every referenced image has been checked. You can then disconnect from
the network. Importing a replacement temporarily needs room for both the old
and new collections; the old files are removed after successful installation.

Some TVs have no Android document picker. The ADB inbox works without one:

```sh
# Enable developer options and network/wireless debugging on the TV.
# Follow the TV's pairing instructions; its port may differ from this example.
adb connect TV_IP:5555
adb install -r painting-tv.apk

# Launch once to create the app's offline collection inbox.
adb shell am start -n com.mateleo.paintingtv/.MainActivity
adb shell am force-stop com.mateleo.paintingtv
adb push painting-pack.zip /sdcard/Android/data/com.mateleo.paintingtv/files/inbox/collection.zip
adb shell am start -n com.mateleo.paintingtv/.MainActivity
```

The next launch imports a changed inbox ZIP. After a successful import you may
delete the inbox ZIP to reclaim space; the app keeps its own extracted images.
If an import fails, fix the issue and push the ZIP again. App storage lives in
Android's app-specific storage and is removed when you uninstall the app.

## Remote controls

- Press a direction or OK to reveal the controls. They disappear after five
  seconds of inactivity.
- With controls hidden, Left/Right go to the previous/next painting. With them
  visible, directions move focus; OK activates the focused button.
- Pause/Play, Next, Previous, and Menu remote keys also work.
- Settings pause playback and remain visible until closed.
- Back closes settings, then hides controls; Back from an unobstructed gallery
  exits the app.

Default display time is **10 seconds**. Choices are 5, 10, 30 seconds, 1, 5,
15 minutes, or 1 hour. Settings persist between launches. Gentle zoom and white
artwork captions start enabled. Fill-screen cropping is the default; select
**whole painting** for black margins. Whole-painting mode suppresses zoom to
keep the edges visible. Each shuffle cycle includes every painting, with no
immediate repeat at the boundary. The app keeps the TV awake while open.

Settings also offers **All / HD+ / 4K+** source-quality filters. The filter
uses the actual source dimensions and selected framing: filling the screen
requires enough pixels in both dimensions; showing a whole portrait with
black margins can qualify by its height. The panel shows how many paintings
qualify and the current image's source dimensions. A dimension check cannot
prove that a scan contains genuine fine detail.

The renderer requests a 4K display mode if the television exposes a matching
refresh-rate mode. Actual UI/output resolution depends on the TV firmware;
decoding a 4K image is not a guarantee that a particular TV renders apps at 4K.

## The collection and high resolution images

Source: [Tableaux de maîtres : les 2000 plus vus](https://ankiweb.net/shared/info/171273480).
The downloaded deck contains **2,160 notes and 2,156 embedded images**.
[catalog/paintings.json](catalog/paintings.json) preserves all note metadata.
Four notes reference missing images. The quality release restores those records
using cited title/artist/date evidence in [catalog/source-overrides.json](catalog/source-overrides.json).
Titles, artists, dates, and movements are preserved as provided by the deck;
they have not been independently fact-checked.

**The original deck images are thumbnails, not 4K scans.** The quality release
includes larger reproductions from WikiArt and Wikimedia Commons where they
pass reference-image comparison, with original-image fallbacks for unresolved
works. It remains a mixed-resolution collection. The complete
[CSV audit](catalog/quality-upgrade-report.csv) records every painting's old and
new dimensions, source, and remaining 4K enlargement requirement. The
[JSON report](catalog/quality-upgrade-report.json) includes overall counts.
Use the app's HD+/4K+ filters to restrict playback to suitable sources.

The legacy text-based Commons resolver below still requires manual approval.
Title similarity alone can select an unrelated painting or another version.
Both source workflows save progress for resuming, including rate limits and
unmatched records. Some works have no available high resolution reproduction.

```sh
python3 -m tools.painting_catalog download
python3 -m tools.painting_catalog extract
python3 -m tools.painting_catalog resolve --limit 20 --delay 2 --resume
# Inspect a candidate's source page and image, then approve it:
python3 -m tools.painting_catalog approve PAINTING_ID --candidate 0
python3 -m tools.painting_catalog pack --min-width 3840
python3 -m tools.painting_catalog bundle
```

See [tools/README.md](tools/README.md) for commands and catalog details. The
source deck, downloaded images, and generated packs stay in ignored `data/`;
the release hosts the prepared pack separately from Git history. Image rights
remain with their respective sources. Keep source and license metadata when
adding replacements. The two starter images are CC0 Met Open Access works;
their source pages and credits are in `app/src/main/assets/catalog.json`.

## Audit and improve every image

Install the optional image tools in a virtual environment (Pillow is the only
extra dependency). With `uv` installed:

```sh
uv venv
uv pip install -e '.[images]'
.venv/bin/python -m tools.image_quality --no-starters
.venv/bin/python -m tools.source_upgrades
.venv/bin/python -m tools.commons_upgrades
.venv/bin/python -m tools.curated_sources
.venv/bin/python -m tools.review_mismatches --apply-decisions catalog/reviewed-source-overrides.json
.venv/bin/python -m tools.build_quality_pack
.venv/bin/python -m tools.quality_review
```

The technical audit fully decodes each available source and records missing
files, dimensions, crop enlargement, hashes, and a clearly labeled edge-detail
heuristic. The source passes save progress and compare downloaded reproductions
against the deck image before accepting an upgrade. Automatic similarity checks
can reject changed crops or colors and are not a substitute for a human review.
Every source attempt is retained, including failures and unmatched paintings.
Candidates rejected by strict comparison can receive a separate model visual
review of the reference and candidate. Accepted exceptions preserve their review
reason and separate provenance in
[catalog/reviewed-source-overrides.json](catalog/reviewed-source-overrides.json);
this does not imply human visual approval. Replaying these decisions requires
the exact reviewed file checksum and larger source dimensions.

Downloaded masters remain unchanged. TV exports use high-quality WebP only
when it saves useful space and meets a conservative compression-error threshold;
otherwise the original JPEG/PNG is retained. Already efficient JPEGs are copied
unchanged, avoiding an unnecessary lossy generation. Source dimensions are
preserved by default; exports never enlarge an image. Optional `--max-edge`
and `--max-pixels` limits can make a smaller TV pack. A requested resize uses
lossless WebP if the lossy version misses the compression-error threshold.

WebP decoding is supported throughout this app's Android version range. AVIF is
not used as the default because Android's documented AVIF support starts at
Android 12 and this TV's version is not yet known. See Android's
[image format support](https://developer.android.com/media/platform/supported-formats#image-formats).
Compression changes storage, not source
detail: the original deck thumbnails still need larger reproductions.

Alternatively, host an app-compatible JSON catalog and its images over HTTPS
and enter its URL under Settings. The app downloads the entire collection,
checks every image, and then activates it. Interrupted downloads can be retried;
completed verified images are reused. URLs must remain stable between retries.
Private GitHub asset URLs require authentication and cannot be pasted directly
into this unauthenticated downloader; use the downloaded ZIP for these releases.

## Build and check

Requires JDK 17 and Android SDK 35 with Build Tools 35.0.0. Open the project in
Android Studio, or set `ANDROID_HOME` to your SDK directory and run:

```sh
./gradlew assembleDebug testDebugUnitTest lintDebug --no-daemon
.venv/bin/python -m unittest discover -s tests -v
```

APK: `app/build/outputs/apk/debug/app-debug.apk`. It is a debug-signed personal
preview build. Keep using the same signing key to install updates without
uninstalling; release/Play distribution needs a private persistent signing key.
No signing key is committed to this repository.

Builds use one worker, a 768 MB Gradle heap, and the Kotlin compiler in-process
to reduce memory use. Image downloads/imports stream to disk. Runtime decodes
one scan at a time with a ceiling of about 8.3 megapixels (roughly 32 MB of
pixel data), lowering that ceiling on TVs with smaller heaps and retaining the
outgoing image briefly during the dissolve.

Automated checks cover shuffled playback, offline catalog/path validation,
Anki extraction, and collection packaging. TV hardware checks still required:
remote focus, USB picker availability, 4K output, sleep/resume, cancellation,
and an import of the full pack on your Philips model. An Android emulator is
deliberately not started on a memory-constrained development machine.

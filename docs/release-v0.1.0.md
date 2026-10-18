First personal preview of Painting TV for Android TV / Google TV (Android 8+).

- Native Kotlin gallery with shuffled cycles and gentle dissolves.
- Remote controls fade after five seconds; timing, zoom, captions, and framing persist.
- Full-screen crop by default; optional whole painting with black margins.
- Resumable HTTPS collection downloads.
- Python tools extract the Anki deck and find reviewable high resolution replacements.

**Assets**

- `painting-tv.apk`: installable debug-signed preview; includes two CC0 Met paintings.
- `SHA256SUMS.txt`: download checksums.

The source deck has 2,160 notes. Four lack embedded image files and are listed
in the source report. The initial collection uses the original small deck images and
**is not 4K**. High resolution candidate matches require review before replacing
an original. All artwork metadata is preserved in the repository catalog.

APK compilation, Kotlin/Python unit tests, Android lint, and validation of
every pack image completed locally. No emulator was started to conserve RAM.
Remote focus, downloads, and 4K output still need verification
on the Philips TV. See the README for USB and ADB installation instructions.

Install the latest app release to download the collection from
[Hugging Face](https://huggingface.co/datasets/Mateleo/painting-tv-collection).
Collection archives are no longer distributed.

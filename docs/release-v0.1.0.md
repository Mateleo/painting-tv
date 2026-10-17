First personal preview of Painting TV for Android TV / Google TV (Android 8+).

- Native Kotlin gallery with shuffled cycles and gentle dissolves.
- Remote controls fade after five seconds; timing, zoom, captions, and framing persist.
- Full-screen crop by default; optional whole painting with black margins.
- Offline ZIP import, ADB inbox, and resumable HTTPS collection downloads.
- Python tools extract the Anki deck and find reviewable high resolution replacements.

**Assets**

- `painting-tv.apk`: installable debug-signed preview; includes two CC0 Met paintings.
- `painting-pack.zip`: 2,156 original deck images, roughly 114 MB. Import from Settings.
- `SHA256SUMS.txt`: download checksums.

The source deck has 2,160 notes. Four lack embedded image files and are listed
in the pack's report. The full pack uses the original small deck images and
**is not 4K**. High resolution candidate matches require review before replacing
an original. All artwork metadata is preserved in the repository catalog.

APK compilation, Kotlin/Python unit tests, Android lint, and validation of
every pack image completed locally. No emulator was started to conserve RAM.
Remote focus, file-picker availability, and 4K output still need verification
on the Philips TV. See the README for USB and ADB installation instructions.

# Painting TV 0.6.0 — screen saver, smaller updates, French interface

- Painting TV can be the TV's screen saver. Choose it in **Settings → System →
  Ambient mode** (or **Screen saver**). On Google TV, set it with ADB as the
  README explains.
- The shuffle continues where it stopped after a restart, and paintings added
  by a download join the current cycle instead of restarting it.
- The next painting is prepared ahead of time, so each change starts on time.
- Settings offers **Download update** when the published collection changes.
  Unchanged paintings are kept; only new or changed ones are downloaded.
- Downloaded images are checked against the SHA-256 in the catalog.
- If the installed collection can no longer be read after an app update,
  Settings opens and offers to download it again.
- The interface follows the TV's language: English or French.

Settings and the downloaded collection are kept. `SHA256SUMS.txt` verifies the
APK download.

This remains a debug-signed personal preview. Validated with the Android build,
JVM unit tests, lint, and Python checks; no TV device test was run for this release.

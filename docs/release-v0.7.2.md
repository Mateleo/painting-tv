# Painting TV 0.7.2 — quicker menus

- Controls and Settings receive focus without the previous fixed 100 ms wait.
- Changing a setting rebuilds less of the interface: unchanged settings rows,
  the painting and captions can be skipped, and download progress updates its
  own section.
- Preparing the next painting pauses while Settings is open or the app is in
  the background. Framing changes still preview immediately.

Settings and the downloaded collection are kept. `SHA256SUMS.txt` verifies the
APK download.

This remains a debug-signed personal preview. Validated with the Android build,
JVM unit tests, lint, Python checks, and Compose compiler reports; no TV device
test or frame-time measurement was run for this release.

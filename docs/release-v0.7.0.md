# Painting TV 0.7.0 — smoother navigation, less CPU

- Settings and the remote controls respond faster: a key press no longer
  redraws the whole screen, and Settings measures free space in the background.
- Pressing Next or Previous several times in a row no longer decodes every
  painting skipped past; only the one you stop on is opened.
- The next painting is prepared at low priority, so it no longer competes with
  the interface.
- Saving the shuffle happens in the background instead of on each key press.
- The progress bar no longer rebuilds the controls on every frame.
- Without slow zoom and with the controls hidden, the slideshow just waits for
  the next painting instead of animating every frame, using less CPU.

Settings and the downloaded collection are kept. `SHA256SUMS.txt` verifies the
APK download.

This remains a debug-signed personal preview. Validated with the Android build,
JVM unit tests, lint, and Python checks; no TV device test was run for this release.

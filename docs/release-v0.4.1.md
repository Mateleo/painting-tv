# Painting TV 0.4.1 — simpler collection downloads

Hugging Face is now the only collection source. Install `painting-tv.apk`, open
Settings, and choose **Download all · 2.9 GB**. Completed paintings join the
gallery while the rest download, and stay available offline. Paused downloads
can still resume.

- Removed file imports and the ADB collection inbox from the app.
- Removed archive packaging and joining tools from the codebase.
- Removed collection archives and their joining helpers from all GitHub releases.

The [Hugging Face dataset](https://huggingface.co/datasets/Mateleo/painting-tv-collection)
is unchanged. Install this APK over the previous version to keep your settings
and downloaded paintings. `SHA256SUMS.txt` verifies the APK download.

This remains a debug-signed personal preview. Validated with the Android build,
JVM unit tests, lint, and Python checks; no TV device test was run for this release.

# Painting TV 0.4.0 — watch while downloading

- Watch paintings while the collection downloads in the background. Several images
  download at once, and finished paintings join the slideshow immediately.
- Cancel to pause a download while keeping completed images; resume to continue.
- New adaptive launcher icon, monochrome variant, labeled TV banner, and dedicated
  download notification icon.
- Updated installation instructions and a photo of Painting TV in action.

Install `painting-tv.apk` over your existing version to keep settings and the
collection. On a new install, open Settings and choose **Download all · 2.9 GB**.
The collection is unchanged from 0.3.0: 2,160 paintings, available offline after
all images finish downloading.

For an offline install, download `painting-pack.zip.001`, `painting-pack.zip.002`,
`painting-pack.parts.json`, and `join-pack.py` into one folder, then run:

```sh
python join-pack.py painting-pack.parts.json --output painting-pack.zip
```

Import the joined ZIP through **Settings → Import ZIP**. Do not import the
individual parts. `SHA256SUMS.txt` lists checksums for the release assets.

This remains a debug-signed personal preview. Built and checked with Android
lint and JVM unit tests; the new launcher artwork and download behavior still
need verification on a TV.

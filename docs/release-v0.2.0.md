Replaces most original deck thumbnails with larger matching reproductions and improves TV decoding of cropped portrait paintings.

- All 2,160 paintings are included; 1,889 have larger sources or restored images. All four missing deck images were recovered from cited title/artist/date evidence.
- Every exported file was fully decoded: zero missing or corrupt images. The ZIP integrity check passed.
- 113 images have enough pixels for native 4K screen fill; 377 qualify for 4K whole-painting mode with margins. The collection remains mixed resolution. Use the app's **All / HD+ / 4K+** filters to choose.
- Every record received a WikiArt source check; an additional 681 records received Commons searches. 271 retain their original deck image. Unfinished Commons searches remain resumable in the tools.
- Source dimensions are preserved. 131 exports use high-quality/lossless WebP where useful; 2,029 retain their original format. Compression saves 230 MB. Lossy candidates must save at least 5% and pass a 43 dB error guard on five native-resolution patches.
- Portrait crops now spend the decode budget on the visible painting area. Decoding remains sequential with a memory budget suited to TV heaps.

Download `painting-tv.apk` and `painting-pack.zip` (about 1.95 GB). Install the APK, then import the ZIP through **Settings → Import collection ZIP**, or use the ADB inbox instructions in the README. Keep sufficient space for the ZIP and extracted collection; replacing a collection temporarily retains the previous files. The pack fits in a single download; no joining is required.

`quality-review.html` is a searchable offline review of every painting. The CSV/JSON audits include old/new dimensions, selected source, format choice, and remaining 4K enlargement. `SHA256SUMS.txt` verifies all downloads. Source URLs, available license metadata, and credits remain in the pack catalog.

Matching is automated image comparison, with separate cited identity checks for the four missing originals. It is not a claim that every replacement received a human visual review; pixel dimensions cannot prove genuine fine detail or color accuracy. No source is enlarged or AI reconstructed.

Validation: 31 Python tests, 17 Kotlin tests, APK compilation and Android lint passed locally; every exported image and the final ZIP were checked. This remains a debug-signed personal preview. Remote focus, import, and actual 4K output still need verification on the Philips TV. See the README for installation and supported image-format references.

# Painting TV 0.5.0 — collections in captions and a lighter catalog

- Captions now name the museum or collection holding the painting, where one is
  known (910 of 2,160 paintings), as "Institution, City".
- The collection catalog the TV downloads is about 0.7 MB instead of 6 MB. French
  titles are now part of the catalog itself.
- The [Hugging Face collection](https://huggingface.co/datasets/Mateleo/painting-collection)
  can now be browsed in the dataset viewer, with each painting's image, source,
  licence and credit.

The catalog format changed. A TV that downloaded the collection with an earlier
version must download it again: open Settings and choose **Download all**.
`SHA256SUMS.txt` verifies the APK download.

This remains a debug-signed personal preview. Validated with the Android build,
JVM unit tests, lint, and Python checks; no TV device test was run for this release.

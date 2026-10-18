# Painting TV 0.3.0 — one-press collection download

Install only the APK; the app now fetches the collection itself.

- On first launch, Settings opens on **Download full collection (about 2.9 GB)**.
  One OK press downloads all 2,160 paintings from the public Hugging Face dataset
  `Mateleo/painting-collection`, checks every image, and then plays offline.
  An interrupted download resumes and keeps finished images.
- 143 more paintings have larger, eye-reviewed reproductions from a research pass
  over Wikidata, museum open-access collections, and artist sites.
- 280 images now have enough pixels for native 4K screen fill (up from 127 in
  0.2.0) and 583 qualify for 4K whole-painting mode with margins (up from 406).
  The collection remains mixed resolution; the **All / HD+ / 4K+** filters still apply.
- Includes the gentle-zoom jump and stuck-slideshow fixes made after 0.2.0.

The collection is hosted on [Hugging Face](https://huggingface.co/datasets/Mateleo/painting-collection).
Use the latest app release to download it. Collection archives are no longer distributed.

The research decisions, with source page, licence, checksum, and review verdict
for each, are now committed in `catalog/research-sources.json`. Identity checks
combine automated image comparison with a paired visual review. Pixel dimensions
cannot prove genuine fine detail. No image is enlarged or AI-generated.

This remains a debug-signed personal preview. Remote focus, the in-app download,
and actual 4K output still need verification on the TV.

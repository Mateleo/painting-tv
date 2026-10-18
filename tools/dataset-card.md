---
pretty_name: Painting collection
license: other
language:
- fr
size_categories:
- 1K<n<10K
configs:
- config_name: default
  data_files:
  - split: train
    path:
    - metadata.jsonl
    - images/*
---

# Painting collection

Painting images and metadata for the Painting TV slideshow, also usable for
browsing and study.

- 2,160 paintings from the shared Anki deck "Tableaux de maîtres : les 2000
  plus vus", with larger reproductions from WikiArt, Wikimedia Commons and
  museum open-access sources where they matched the deck image.
- Source dimensions are preserved; nothing is upscaled or AI-generated.
- Titles are in French. Dates are as given by the deck.
- `collection` names the holding institution where one is known. It is often
  taken from the matched WikiArt page, so treat it as indicative.

## Files

- `images/`: one image per painting (JPEG, PNG or WebP).
- `metadata.jsonl`: one row per painting, shown by the dataset viewer: title,
  artist, year, movement, collection, pixel size, file size and SHA-256, the
  reproduction's source and source page, licence and credit.
- `catalog.json`: the compact catalog the Painting TV app downloads. Its
  `imageUrl` paths are relative to this folder, and each image's `sha256` lets
  the app verify it.

## Rights

This is a mixed-rights collection. Many works are public domain, some files
carry Creative Commons licences (see `license`), and some 20th-century works
remain in copyright with their artists' estates. Rights stay with their
respective holders. It is published for personal, non-commercial viewing.
Rights holders who want a work removed can open a discussion on this dataset
and it will be taken down.

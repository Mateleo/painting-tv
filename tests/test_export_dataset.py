import json
from pathlib import Path
from unittest.mock import patch

from tools.export_dataset import export_dataset


def build_pack(pack: Path) -> None:
    (pack / "images").mkdir(parents=True)
    (pack / "images/a.jpg").write_bytes(b"image a")
    painting = {
        "id": "a", "title": "The Starry Night", "artist": "Vincent van Gogh", "year": "1889",
        "movement": "", "imageUrl": "images/a.jpg", "width": 3840, "height": 3041,
        "sourceUrl": "https://example.org/a", "license": "Public domain",
        "collection": "Collection unknown",
        "collectionResearch": {"status": "unknown-after-research", "researchTrail": {}},
        "sourceSelection": {"source": "WikiArt", "sha256": "master", "credit": "Credit"},
        "compression": {"outputBytes": 7},
    }
    (pack / "catalog.json").write_text(json.dumps({"version": 1, "paintings": [painting]}))


def test_export_keeps_app_fields_and_publishes_no_research(tmp_path):
    pack, output = tmp_path / "pack", tmp_path / "out"
    build_pack(pack)
    (output / "images").mkdir(parents=True)
    (output / "images/stale.jpg").write_bytes(b"old")
    titles = tmp_path / "titles.json"
    titles.write_text(json.dumps({"a": "La Nuit étoilée"}))
    collections = tmp_path / "collections.json"
    collections.write_text(json.dumps({"a": "Museum of Modern Art"}))
    card = tmp_path / "card.md"
    card.write_text("card")
    with patch("tools.common.COLLECTIONS", collections):
        counts = export_dataset(pack, output, titles, card)

    assert counts == {"paintings": 1, "frenchTitles": 1, "withCollection": 1}
    catalog = json.loads((output / "catalog.json").read_text())
    assert catalog["version"] == 2
    assert catalog["paintings"] == [{
        "id": "a", "title": "La Nuit étoilée", "artist": "Vincent van Gogh", "year": "1889",
        "collection": "Museum of Modern Art", "imageUrl": "images/a.jpg", "width": 3840,
        "height": 3041, "license": "Public domain", "sourceUrl": "https://example.org/a",
    }]
    (row,) = [json.loads(line) for line in (output / "metadata.jsonl").read_text().splitlines()]
    assert row["file_name"] == "images/a.jpg" and row["source"] == "WikiArt" and row["bytes"] == 7
    published = (output / "catalog.json").read_text() + (output / "metadata.jsonl").read_text()
    assert "research" not in published.lower()
    assert sorted(p.name for p in (output / "images").iterdir()) == ["a.jpg"]
    assert (output / "README.md").read_text() == "card"


def test_paintings_missing_from_the_label_map_have_no_collection(tmp_path):
    pack = tmp_path / "pack"
    build_pack(pack)
    with patch("tools.common.COLLECTIONS", tmp_path / "absent.json"):
        export_dataset(pack, tmp_path / "out", tmp_path / "absent-titles.json", pack / "catalog.json")
    (painting,) = json.loads((tmp_path / "out/catalog.json").read_text())["paintings"]
    assert "collection" not in painting and painting["title"] == "The Starry Night"

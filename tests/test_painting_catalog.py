import json
import sqlite3
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.painting_catalog import (
    approve_candidate,
    download_pack,
    extract_apkg,
    image_dimensions,
    protobuf_fields,
    resolve_catalog,
    strip_html,
)


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        if size < 0:
            size = len(self.data)
        result, self.data = self.data[:size], self.data[size:]
        return result


class CatalogTests(unittest.TestCase):
    def test_refresh_preserves_approved_matches(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            item = {"id": "approved", "resolution": {"status": "approved", "candidates": []}}
            path.write_text(json.dumps({"version": 1, "paintings": [item]}))
            with patch("tools.painting_catalog.commons_candidates") as lookup:
                self.assertEqual(resolve_catalog(path, delay=0, resume=False), 0)
                lookup.assert_not_called()
            self.assertEqual(json.loads(path.read_text())["paintings"][0], item)

    def test_repeated_throttling_stops_batch_with_progress_saved(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            records = [{"id": str(i), "resolution": {"status": "unresolved"}} for i in range(10)]
            path.write_text(json.dumps({"version": 1, "paintings": records}))
            error = urllib.error.HTTPError("https://example.org", 429, "Rate limited", {}, None)
            with patch("tools.painting_catalog.commons_candidates", side_effect=error) as lookup:
                self.assertEqual(resolve_catalog(path, delay=0), 3)
                self.assertEqual(lookup.call_count, 3)
            saved = json.loads(path.read_text())["paintings"]
            self.assertEqual(saved[2]["resolution"]["status"], "lookup-error")
            self.assertEqual(saved[3]["resolution"]["status"], "unresolved")

    def test_protobuf_wire_fields(self):
        self.assertEqual(
            list(protobuf_fields(b"\x0a\x02ok\x10\x96\x01")), [(1, 2, b"ok"), (2, 0, 150)]
        )

    def test_strip_html(self):
        self.assertEqual(
            strip_html("<b>Étoile</b><br>du soir &amp; matin"), "Étoile du soir & matin"
        )

    def test_png_dimensions(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.png"
            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + b"\0" * 4
                + b"IHDR"
                + (640).to_bytes(4, "big")
                + (480).to_bytes(4, "big")
            )
            self.assertEqual(image_dimensions(path), (640, 480))

    def test_extract_apkg_maps_named_fields_and_media(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            apkg = base / "mini.apkg"
            conn = sqlite3.connect(":memory:")
            conn.execute("create table col(models text)")
            models = {
                "1": {
                    "flds": [
                        {"name": name}
                        for name in (
                            "Artwork",
                            "Artist",
                            "Title",
                            "Date",
                            "Period/Movement",
                            "Medium",
                        )
                    ]
                }
            }
            conn.execute("insert into col values (?)", (json.dumps(models),))
            conn.execute("create table notes(id integer, mid integer, flds text, tags text)")
            conn.execute(
                "insert into notes values (1, 1, ?, ' tag ')",
                ("<img src='work.jpg'>\x1fArtist\x1fTitle\x1f1900\x1fStyle\x1fOil",),
            )
            conn.commit()
            with zipfile.ZipFile(apkg, "w") as z:
                z.writestr("collection.anki2", b"placeholder written by newer Anki exports")
                z.writestr("collection.anki21", conn.serialize())
                z.writestr("media", json.dumps({"0": "work.jpg"}))
                z.writestr("0", b"image data")
            result = extract_apkg(apkg, base / "out")
            self.assertEqual(len(result), 1)
            self.assertEqual(
                (result[0]["title"], result[0]["artist"], result[0]["year"]),
                ("Title", "Artist", "1900"),
            )
            self.assertEqual(result[0]["imageUrl"], "images/work.jpg")
            self.assertTrue((base / "out" / "images" / "work.jpg").exists())

    def test_approve_candidate_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            candidate = {
                "source": "Commons",
                "imageUrl": "https://example.org/a.jpg",
                "width": 4000,
                "height": 3000,
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:A.jpg",
                "license": "PD",
            }
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "paintings": [{"id": "x", "resolution": {"candidates": [candidate]}}],
                    }
                )
            )
            approve_candidate(path, "x")
            item = json.loads(path.read_text())["paintings"][0]
            self.assertEqual(item["resolution"]["status"], "approved")
            self.assertEqual(item["imageUrl"], candidate["imageUrl"])
            self.assertEqual(item["originalImageUrl"], "")

    def test_resolve_limit_counts_pending_records_and_resume_skips_reviewed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            records = [
                {
                    "id": "reviewed",
                    "title": "A",
                    "artist": "B",
                    "resolution": {
                        "status": "needs-review",
                        "candidates": [{"title": "candidate"}],
                    },
                },
                {
                    "id": "unresolved",
                    "title": "C",
                    "artist": "D",
                    "resolution": {"status": "unresolved", "candidates": []},
                },
                {
                    "id": "later",
                    "title": "E",
                    "artist": "F",
                    "resolution": {"status": "unresolved", "candidates": []},
                },
            ]
            path.write_text(json.dumps({"version": 1, "paintings": records}))
            with patch("tools.painting_catalog.commons_candidates", return_value=[]) as lookup:
                self.assertEqual(resolve_catalog(path, limit=1, delay=0, resume=True), 1)
                lookup.assert_called_once()
            saved = json.loads(path.read_text())["paintings"]
            self.assertEqual(saved[1]["resolution"]["status"], "no-candidates")
            self.assertEqual(saved[2]["resolution"]["status"], "unresolved")

    def test_pack_persists_each_approved_download_for_resume(self):
        png = (
            b"\x89PNG\r\n\x1a\n"
            + b"\0" * 4
            + b"IHDR"
            + (640).to_bytes(4, "big")
            + (480).to_bytes(4, "big")
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            catalog_path = root / "catalog.json"
            candidate = {
                "imageUrl": "https://example.org/high.png",
                "width": 640,
                "height": 480,
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:High",
                "license": "PD",
            }
            painting = {
                "id": "x",
                "title": "Title",
                "artist": "Artist",
                "imageUrl": candidate["imageUrl"],
                "width": 640,
                "height": 480,
                "sourceUrl": candidate["sourceUrl"],
                "license": "PD",
                "resolution": {"status": "approved", "candidates": [candidate]},
            }
            catalog_path.write_text(json.dumps({"version": 1, "paintings": [painting]}))
            with patch(
                "tools.painting_catalog.urllib.request.urlopen", return_value=FakeResponse(png)
            ):
                self.assertEqual(download_pack(catalog_path, root / "offline" / "images"), 1)
            saved = json.loads(catalog_path.read_text())["paintings"][0]
            self.assertEqual(saved["resolution"]["offlineImage"], "offline/images/x.png")
            self.assertEqual((root / saved["resolution"]["offlineImage"]).read_bytes(), png)


if __name__ == "__main__":
    unittest.main()

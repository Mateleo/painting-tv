import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.painting_catalog import (
    extract_apkg,
    image_dimensions,
    protobuf_fields,
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


if __name__ == "__main__":
    unittest.main()

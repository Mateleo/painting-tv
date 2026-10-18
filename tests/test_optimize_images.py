import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.optimize_images import build_pack, optimize_one


class CompressionTests(unittest.TestCase):
    def test_lossless_webp_preserves_all_pixels_for_flat_png(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.png"
            with Image.new("RGB", (512, 512), (37, 102, 197)) as image:
                image.save(source)
            result = optimize_one(source, root / "out/image")
            with Image.open(source) as before, Image.open(result["path"]) as after:
                self.assertEqual(before.tobytes(), after.convert("RGB").tobytes())
            self.assertFalse(result["upscaled"])

    def test_never_enlarges_small_originals(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "tiny.jpg"
            with Image.new("RGB", (32, 48), (200, 180, 140)) as image:
                image.save(source, quality=80)
            result = optimize_one(source, root / "out/image")
            self.assertEqual((result["width"], result["height"]), (32, 48))

    def test_retains_transparency_in_original(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "alpha.png"
            with Image.new("RGBA", (128, 128), (250, 0, 0, 75)) as image:
                image.save(source)
            result = optimize_one(source, root / "out/image", max_edge=64)
            self.assertEqual(result["formatDecision"], "original-kept")
            self.assertEqual(Path(result["path"]).read_bytes(), source.read_bytes())
            self.assertEqual((result["width"], result["resizedForTV"]), (128, False))

    def test_large_master_is_unchanged_and_tv_export_obeys_limits(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "master.jpg"
            with Image.new("RGB", (1400, 900), (20, 100, 80)) as image:
                image.save(source)
            original = source.read_bytes()
            result = optimize_one(source, root / "out/image", max_edge=700, max_pixels=250_000)
            self.assertEqual(source.read_bytes(), original)
            self.assertLessEqual(max(result["width"], result["height"]), 700)
            self.assertLessEqual(result["width"] * result["height"], 250_000)

    def test_dataset_can_resume_and_catalog_references_readable_images(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with Image.new("RGB", (64, 64), "blue") as image:
                image.save(root / "source.jpg")
            path = root / "catalog.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "paintings": [
                            {
                                "id": "work",
                                "title": "Work",
                                "artist": "Artist",
                                "imageUrl": "source.jpg",
                            },
                            {"id": "missing", "title": "Absent", "imageUrl": ""},
                        ],
                    }
                )
            )
            result = build_pack(path, root / "pack")
            result2 = build_pack(path, root / "pack")
            self.assertEqual(result["outputBytes"], result2["outputBytes"])
            self.assertEqual(result["recordsChecked"], 2)
            self.assertEqual(result["included"], 1)
            catalog = json.loads((root / "pack/catalog.json").read_text())
            self.assertEqual(len(catalog["paintings"]), 1)
            with Image.open(root / "pack" / catalog["paintings"][0]["imageUrl"]) as image:
                self.assertEqual(image.size, (64, 64))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.image_quality import audit_image, run_audit, write_compact


class ImageQualityTests(unittest.TestCase):
    def test_full_decode_and_4k_crop_geometry(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.jpg"
            Image.new("RGB", (1920, 1080), "white").save(path, quality=90)
            result = audit_image(path, entry_id="x")
            self.assertEqual(result["status"], "ok")
            self.assertEqual((result["width"], result["height"]), (1920, 1080))
            self.assertEqual((result["crop_visible_width"], result["crop_visible_height"]), (1920, 1080))
            self.assertEqual(result["upscale_factor"], 2.0)
            self.assertIn("upscale-for-4k-crop", result["flags"])

    def test_missing_and_corrupt_files_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(audit_image(root / "missing.jpg", entry_id="m")["status"], "missing")
            broken = root / "broken.jpg"
            broken.write_bytes(b"not an image")
            self.assertEqual(audit_image(broken, entry_id="b")["status"], "corrupt")

    def test_catalog_audit_and_compact_output_include_every_record(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "images").mkdir()
            Image.new("RGB", (3840, 2160), "black").save(root / "images" / "one.jpg")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"paintings": [
                {"id": "one", "imageUrl": "images/one.jpg"},
                {"id": "absent", "imageUrl": "images/absent.jpg"},
            ]}))
            report = run_audit(catalog, repo_root=root)
            self.assertEqual((report["record_count"], report["ok_count"], report["missing_count"]), (2, 1, 1))
            compact = root / "audit.json"
            write_compact(report, compact)
            self.assertEqual(json.loads(compact.read_text())["record_count"], 2)


if __name__ == "__main__":
    unittest.main()

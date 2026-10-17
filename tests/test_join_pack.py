import tempfile
import unittest
from pathlib import Path

from tools.join_pack import join_pack, split_pack


class SplitPackTests(unittest.TestCase):
    def test_parts_join_to_exact_original_with_bounded_chunk_sizes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = root / "original.zip"
            original.write_bytes(bytes(range(256)) * 50)
            manifest = split_pack(original, root / "parts", part_size=1000)
            joined = root / "joined.zip"
            join_pack(manifest, joined)
            self.assertEqual(original.read_bytes(), joined.read_bytes())
            self.assertTrue(all(p.stat().st_size <= 1000 for p in manifest.parent.glob("*.0*")))

    def test_corrupt_part_does_not_replace_existing_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = root / "original.zip"
            original.write_bytes(b"valid" * 100)
            manifest = split_pack(original, root / "parts", part_size=100)
            next(manifest.parent.glob("*.001")).write_bytes(b"corrupt")
            output = root / "joined.zip"
            output.write_bytes(b"keep me")
            with self.assertRaises(ValueError):
                join_pack(manifest, output)
            self.assertEqual(output.read_bytes(), b"keep me")
            self.assertFalse((root / "joined.zip.partial").exists())

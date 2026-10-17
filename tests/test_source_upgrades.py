import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from tools import source_upgrades as upgrades


def image_bytes(size, color="navy"):
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4), fill="gold")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=96)
    return out.getvalue()


class SourceUpgradeTests(unittest.TestCase):
    def test_wikiart_slug_overrides_and_size_suffix(self):
        self.assertEqual(
            upgrades.source_page_for("images/leonard-de-vinci_la-joconde-1504.jpg"),
            "https://www.wikiart.org/en/leonardo-da-vinci/mona-lisa",
        )
        self.assertEqual(
            upgrades.source_page_for("images/test-artist_sample-title-1900.jpg"),
            "https://www.wikiart.org/en/test-artist/sample-title-1900",
        )
        self.assertEqual(
            upgrades.source_page_candidates("images/test-artist_sample-title-1900.jpg")[1],
            "https://www.wikiart.org/en/test-artist/sample-title",
        )
        mucha_urls = upgrades.source_page_candidates("images/alfons-mucha_example-work-1900.jpg")
        self.assertEqual(
            mucha_urls[1], "https://www.wikiart.org/en/alphonse-mucha/example-work-1900"
        )
        html = '<meta property="og:image" content="https://uploads0.wikiart.org/images/a/b(1).jpg!Large.jpg" />'
        self.assertEqual(
            upgrades.extract_image_url(html), "https://uploads0.wikiart.org/images/a/b(1).jpg"
        )

    def test_visual_comparison_and_full_upgrade_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            images = root / "images"
            images.mkdir()
            Image.open(io.BytesIO(image_bytes((100, 100)))).save(
                images / "test-artist_sample-title-1900.jpg"
            )
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "paintings": [
                            {
                                "id": "art-1",
                                "artist": "Artist",
                                "title": "Title",
                                "imageUrl": "images/test-artist_sample-title-1900.jpg",
                            }
                        ],
                    }
                )
            )
            candidate_url = "https://uploads0.wikiart.org/images/test-artist/sample-title.jpg"
            page = f'<meta property="og:image" content="{candidate_url}!Large.jpg" />'.encode()
            high_res = image_bytes((240, 240))

            def fake_request(url, **_kwargs):
                return page if "wikiart.org/en/" in url else high_res

            with patch.object(upgrades, "_request", side_effect=fake_request):
                summary = upgrades.run_pass(
                    catalog_path, root / "upgrades", workers=1, resume=False
                )
            self.assertEqual(summary["accepted_count"], 1)
            output = json.loads((root / "upgrades/catalog.json").read_text())
            record = output["paintings"][0]
            self.assertEqual(record["imageUrl"], "../images/test-artist_sample-title-1900.jpg")
            self.assertEqual(record["upgradedImageUrl"], "../masters/art-1.jpg")
            self.assertEqual((root / "masters/art-1.jpg").read_bytes(), high_res)
            state = json.loads((root / "upgrades/state.json").read_text())
            self.assertEqual(state["records"]["art-1"]["status"], "accepted")

    def test_wrong_art_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "ref.jpg"
            Image.open(io.BytesIO(image_bytes((100, 100), "navy"))).save(ref)
            result = upgrades.visual_match(ref, image_bytes((200, 200), "red"))
            self.assertFalse(result["match"])

    def test_request_percent_encodes_unicode_and_preserves_existing_escapes(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, size=-1):
                return b"ok"

        with patch(
            "tools.source_upgrades.urllib.request.urlopen", return_value=Response()
        ) as open_url:
            self.assertEqual(
                upgrades._request("https://uploads.wikiart.org/images/café/a%20b.jpg?x=a%2Fb"),
                b"ok",
            )
        request = open_url.call_args.args[0]
        self.assertEqual(
            request.full_url, "https://uploads.wikiart.org/images/caf%C3%A9/a%20b.jpg?x=a%2Fb"
        )

    def test_matched_png_candidate_is_preserved_under_master_contract_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            images = root / "images"
            images.mkdir()
            (images / "test-artist_sample-title-1900.jpg").write_bytes(image_bytes((100, 100)))
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "paintings": [
                            {"id": "png-1", "imageUrl": "images/test-artist_sample-title-1900.jpg"}
                        ]
                    }
                )
            )
            candidate_url = "https://uploads0.wikiart.org/images/test-artist/sample-title.png"
            page = f'<meta property="og:image" content="{candidate_url}!Large.jpg" />'.encode()
            candidate_out = io.BytesIO()
            image = Image.new("RGB", (220, 220), "navy")
            draw = ImageDraw.Draw(image)
            draw.rectangle((55, 55, 165, 165), fill="gold")
            image.save(candidate_out, "PNG")

            def fake_request(url, **_kwargs):
                return page if "wikiart.org/en/" in url else candidate_out.getvalue()

            with patch.object(upgrades, "_request", side_effect=fake_request):
                summary = upgrades.run_pass(
                    catalog_path, root / "upgrades", workers=1, resume=False
                )
            self.assertEqual(summary["accepted_count"], 1)
            master = root / "masters/png-1.jpg"
            self.assertTrue(master.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_exact_year_slug_falls_back_to_yearless_only_on_404(self):
        urls = upgrades.source_page_candidates("images/test-artist_sample-title-1900.jpg")
        page = b'<meta property="og:image" content="https://uploads0.wikiart.org/images/a/b.jpg!Large.jpg" />'
        calls = []

        def fake_request(url, **_kwargs):
            calls.append(url)
            if url == urls[0]:
                import urllib.error

                error = urllib.error.HTTPError(url, 404, "Not Found", {}, None)
                error.close()
                raise error
            if url == urls[1]:
                return page
            return image_bytes((100, 100))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "images").mkdir()
            (root / "images/sample.jpg").write_bytes(image_bytes((100, 100)))
            record = {
                "id": "x",
                "artist": "artist",
                "title": "sample",
                "imageUrl": "images/sample.jpg",
            }
            # Use the source path stem for page variants, while the record's local image remains the reference.
            with (
                patch.object(
                    upgrades,
                    "_candidate_for",
                    return_value=("\n".join(urls), root / "images/sample.jpg", ""),
                ),
                patch.object(upgrades, "_request", side_effect=fake_request),
            ):
                result = upgrades.process_record(record, root, root / "masters")
        self.assertEqual(calls[:2], urls)
        self.assertEqual(result["status"], "candidate-not-higher-resolution")


if __name__ == "__main__":
    unittest.main()

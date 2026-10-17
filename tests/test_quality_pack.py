import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from tools.build_quality_pack import merge_sources, report_every_record
from tools.commons_upgrades import Client, RateLimited, run


class QualityPackTests(unittest.TestCase):
    def test_merge_chooses_larger_verified_source_and_preserves_every_record(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "old.jpg").write_bytes(b"old")
            (root / "wiki.jpg").write_bytes(b"wiki")
            (root / "commons.jpg").write_bytes(b"commons")
            catalog = root / "catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "paintings": [
                            {"id": "one", "imageUrl": "old.jpg"},
                            {"id": "missing", "imageUrl": ""},
                        ]
                    }
                )
            )
            wiki = root / "wiki-state.json"
            wiki.write_text(
                json.dumps(
                    {
                        "records": {
                            "one": {
                                "status": "accepted",
                                "master_path": "wiki.jpg",
                                "candidate_dimensions": [2000, 1400],
                            }
                        }
                    }
                )
            )
            commons = root / "commons-state.json"
            commons.write_text(
                json.dumps(
                    {
                        "records": {
                            "one": {
                                "status": "accepted",
                                "master_path": str(root / "commons.jpg"),
                                "candidate_dimensions": [4000, 2800],
                                "selected": {
                                    "sourceUrl": "https://commons.wikimedia.org/wiki/File:Example",
                                    "license": "CC0",
                                },
                            }
                        }
                    }
                )
            )
            output = root / "selected/catalog.json"
            report = merge_sources(catalog, wiki, commons, output)
            rows = json.loads(output.read_text())["paintings"]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["sourceSelection"]["source"], "Wikimedia Commons")
            self.assertEqual(rows[0]["license"], "CC0")
            self.assertEqual(rows[1]["imageUrl"], "")
            self.assertEqual(report["selectedSources"]["missing"], 1)

    def test_final_report_accounts_for_missing_notes_as_well_as_exported_images(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "pack"
            pack.mkdir()
            with Image.new("RGB", (640, 480), "green") as image:
                image.save(pack / "one.jpg")
            base = root / "base.json"
            base.write_text(
                json.dumps(
                    {
                        "paintings": [
                            {"id": "one", "title": "Work", "width": 400, "height": 300},
                            {"id": "missing", "title": "Absent"},
                        ]
                    }
                )
            )
            selected = root / "selected.json"
            selected.write_text(
                json.dumps(
                    {
                        "paintings": [
                            {"id": "one", "sourceSelection": {"source": "WikiArt"}},
                            {"id": "missing"},
                        ]
                    }
                )
            )
            (pack / "catalog.json").write_text(
                json.dumps(
                    {
                        "paintings": [
                            {"id": "one", "imageUrl": "one.jpg", "width": 640, "height": 480}
                        ]
                    }
                )
            )
            output = root / "report.json"
            result = report_every_record(base, selected, pack, output)
            self.assertEqual(
                (result["recordsChecked"], result["readable"], result["missing"]), (2, 1, 1)
            )
            self.assertEqual(result["improved"], 1)
            self.assertTrue(output.with_suffix(".csv").exists())

    def test_reviewed_match_keeps_distinct_provenance_and_rejection_is_not_selected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "old.jpg").write_bytes(b"old")
            (root / "review.jpg").write_bytes(b"larger")
            catalog = root / "catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "paintings": [
                            {"id": "accepted", "imageUrl": "old.jpg"},
                            {"id": "rejected", "imageUrl": "old.jpg"},
                        ]
                    }
                )
            )
            reviewed = root / "reviewed.json"
            reviewed.write_text(
                json.dumps(
                    {
                        "records": {
                            "accepted": {
                                "status": "accepted",
                                "master_path": "review.jpg",
                                "candidate_dimensions": [4000, 3000],
                                "method": "model visual review",
                                "source_page_url": "https://www.wikiart.org/example",
                            },
                            "rejected": {
                                "status": "rejected",
                                "master_path": "review.jpg",
                                "candidate_dimensions": [4000, 3000],
                            },
                        }
                    }
                )
            )
            output = root / "selected.json"
            report = merge_sources(
                catalog,
                root / "absent-wiki.json",
                root / "absent-commons.json",
                output,
                reviewed_path=reviewed,
            )
            rows = json.loads(output.read_text())["paintings"]
            self.assertEqual(rows[0]["sourceSelection"]["method"], "model visual review")
            self.assertEqual(rows[0]["sourceSelection"]["source"], "WikiArt (visual review)")
            self.assertEqual(rows[1]["sourceSelection"]["source"], "embedded deck image")
            self.assertEqual(report["modelVisualReviews"], 2)

    def test_research_match_beats_smaller_commons_record_with_distinct_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "old.jpg").write_bytes(b"old")
            (root / "commons.jpg").write_bytes(b"commons")
            (root / "research.jpg").write_bytes(b"larger")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"paintings": [{"id": "a", "imageUrl": "old.jpg"}]}))
            commons = root / "commons.json"
            commons.write_text(
                json.dumps(
                    {
                        "records": {
                            "a": {
                                "status": "accepted",
                                "master_path": "commons.jpg",
                                "candidate_dimensions": [2000, 1500],
                            }
                        }
                    }
                )
            )
            research = root / "research.json"
            research.write_text(
                json.dumps(
                    {
                        "records": {
                            "a": {
                                "status": "accepted",
                                "master_path": "research.jpg",
                                "candidate_dimensions": [6000, 4500],
                                "source_page_url": "https://commons.wikimedia.org/example",
                            }
                        }
                    }
                )
            )
            output = root / "selected.json"
            report = merge_sources(
                catalog,
                root / "absent-wiki.json",
                commons,
                output,
                research_path=research,
            )
            row = json.loads(output.read_text())["paintings"][0]
            self.assertEqual(row["sourceSelection"]["source"], "Researched source")
            self.assertEqual((row["width"], row["height"]), (6000, 4500))
            self.assertEqual(row["imageUrl"], "research.jpg")
            self.assertEqual(report["commonsRecordsChecked"], 1)
            self.assertEqual(report["researchRecordsChecked"], 1)

    def test_commons_rate_limit_saves_progress_and_stops_requests(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"paintings": [{"id": "one"}, {"id": "two"}]}))
            with patch.object(Client, "candidates", side_effect=RateLimited("429")) as request:
                result = run(catalog, root / "output", delay=0.2)
                request.assert_called_once()
            self.assertEqual(result["records"], 1)
            saved = json.loads((root / "output/state.json").read_text())
            self.assertEqual(saved["records"]["one"]["status"], "rate-limited")

    def test_large_commons_scans_request_a_derivative_and_keep_original_provenance(self):
        candidate = {
            "fileTitle": "File:Scan.jpg",
            "width": 30_000,
            "height": 20_000,
            "imageUrl": "https://original.example/scan.jpg",
        }
        response = {
            "query": {
                "pages": {
                    "1": {
                        "imageinfo": [
                            {
                                "thumburl": "https://thumb.example/5000px.jpg",
                                "thumbwidth": 5000,
                                "thumbheight": 3333,
                            }
                        ]
                    }
                }
            }
        }
        with patch.object(Client, "get", return_value=json.dumps(response).encode()):
            address = Client().display_derivative(candidate)
        self.assertEqual(address, "https://thumb.example/5000px.jpg")
        self.assertEqual(candidate["imageUrl"], "https://original.example/scan.jpg")
        self.assertTrue(candidate["downloadIsDerivative"])

    def test_missing_derivative_page_is_a_candidate_error(self):
        with patch.object(Client, "get", return_value=b'{"query": {"pages": {}}}'):
            with self.assertRaises(ValueError):
                Client().display_derivative({"fileTitle": "File:X.jpg", "width": 9, "height": 9})

    def test_very_tall_derivative_also_respects_pixel_memory_budget(self):
        from urllib.parse import parse_qs, urlsplit

        candidate = {"fileTitle": "File:Scroll.jpg", "width": 4000, "height": 80_000}
        response = {
            "query": {
                "pages": {"1": {"imageinfo": [{"thumburl": "https://thumb.example/scroll.jpg"}]}}
            }
        }
        with patch.object(Client, "get", return_value=json.dumps(response).encode()) as request:
            Client().display_derivative(candidate)
        width = int(parse_qs(urlsplit(request.call_args.args[0]).query)["iiurlwidth"][0])
        self.assertLessEqual(width * width * 20, 32_000_000)


if __name__ == "__main__":
    unittest.main()

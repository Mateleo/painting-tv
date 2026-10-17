import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.review_mismatches import apply_decisions


class ReviewMismatchTests(unittest.TestCase):
    def test_changed_candidate_hash_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            master = root / "candidate.jpg"
            master.write_bytes(b"verified locally")
            state_path = root / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "records": {
                            "art-1": {
                                "download_status": "ok",
                                "master_path": str(master),
                                "candidate_sha256": "new-hash",
                                "candidate_dimensions": [200, 200],
                                "original_visual_match": {"reference_dimensions": [100, 100]},
                            }
                        }
                    }
                )
            )
            review_path = root / "review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "id": "art-1",
                                "accepted": True,
                                "candidate_sha256": "old-hash",
                                "method": "model visual review",
                                "reason": "same composition",
                                "visual_match": {},
                            }
                        ]
                    }
                )
            )

            counts = apply_decisions(review_path, state_path, root / "report.json")

            self.assertEqual(counts, {"accepted": 0, "rejected": 0, "stale": 1})
            saved = json.loads(state_path.read_text())["records"]["art-1"]
            self.assertNotIn("accepted", saved)

    def test_replay_checks_actual_file_and_emits_merger_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            master = root / "candidate.jpg"
            master.write_bytes(b"reviewed pixels")
            digest = hashlib.sha256(master.read_bytes()).hexdigest()
            state_path, review_path = root / "state.json", root / "review.json"
            state_path.write_text(
                json.dumps(
                    {
                        "records": {
                            "art": {
                                "download_status": "ok",
                                "master_path": str(master),
                                "candidate_sha256": digest,
                                "candidate_dimensions": [200, 200],
                                "original_visual_match": {"reference_dimensions": [100, 100]},
                            }
                        }
                    }
                )
            )
            review_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "id": "art",
                                "accepted": True,
                                "candidate_sha256": digest,
                                "method": "model visual review",
                                "reason": "same composition",
                            }
                        ]
                    }
                )
            )
            counts = apply_decisions(review_path, state_path, root / "report.json")
            self.assertEqual(counts["accepted"], 1)
            self.assertEqual(
                json.loads(state_path.read_text())["records"]["art"]["status"], "accepted"
            )
            master.write_bytes(b"different artwork")
            counts = apply_decisions(review_path, state_path, root / "report.json")
            self.assertEqual(counts["stale"], 1)
            self.assertEqual(
                json.loads(state_path.read_text())["records"]["art"]["status"], "needs-review"
            )


if __name__ == "__main__":
    unittest.main()

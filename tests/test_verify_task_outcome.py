from __future__ import annotations
import hashlib
import tempfile
import unittest
from pathlib import Path
from tools.verify_task_outcome import assess

class TaskOutcomeVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "proof.txt").write_text("task completed", encoding="utf-8")
        digest = hashlib.sha256(b"task completed").hexdigest()
        self.bundle = {
            "schema": "dreamco.task_outcome_evidence.v1",
            "task": {"id": "task-001", "success_criteria": [
                {"id": "artifact-created", "description": "Expected artifact exists"}
            ]},
            "evidence": [{
                "id": "proof-1", "path": "proof.txt", "sha256": digest,
                "source": "local-test-fixture", "observed_at": "2026-11-08T18:00:00-06:00"
            }],
            "criterion_results": [{
                "criterion_id": "artifact-created", "status": "pass",
                "evidence_ids": ["proof-1"]
            }]
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_hashed_evidence_verifies_success(self):
        result = assess(self.bundle, self.root)
        self.assertEqual(result["status"], "verified_success")
        self.assertTrue(result["verified_success"])

    def test_explicit_failure_is_failed(self):
        self.bundle["criterion_results"][0]["status"] = "fail"
        self.assertEqual(assess(self.bundle, self.root)["status"], "failed")

    def test_unknown_is_inconclusive(self):
        self.bundle["criterion_results"][0]["status"] = "unknown"
        self.assertEqual(assess(self.bundle, self.root)["status"], "inconclusive")

    def test_missing_result_is_inconclusive(self):
        self.bundle["criterion_results"] = []
        result = assess(self.bundle, self.root)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(any("missing result" in error for error in result["errors"]))

    def test_hash_mismatch_is_inconclusive(self):
        self.bundle["evidence"][0]["sha256"] = "0" * 64
        result = assess(self.bundle, self.root)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(any("SHA-256 mismatch" in error for error in result["errors"]))

    def test_path_traversal_is_rejected(self):
        self.bundle["evidence"][0]["path"] = "../outside.txt"
        result = assess(self.bundle, self.root)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(any("outside evidence root" in error for error in result["errors"]))

    def test_duplicate_evidence_ids_are_rejected(self):
        self.bundle["evidence"].append(dict(self.bundle["evidence"][0]))
        result = assess(self.bundle, self.root)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(any("duplicate evidence id" in error for error in result["errors"]))

    def test_timezone_naive_timestamp_is_rejected(self):
        self.bundle["evidence"][0]["observed_at"] = "2026-11-08T18:00:00"
        result = assess(self.bundle, self.root)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(any("timezone-aware" in error for error in result["errors"]))

    def test_wrong_schema_is_inconclusive(self):
        self.bundle["schema"] = "wrong"
        self.assertEqual(assess(self.bundle, self.root)["status"], "inconclusive")

    def test_non_string_evidence_reference_is_rejected(self):
        self.bundle["criterion_results"][0]["evidence_ids"] = [{"unexpected": "object"}]
        result = assess(self.bundle, self.root)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(any("non-empty string evidence_ids" in error for error in result["errors"]))

    def test_invalid_result_type_is_rejected(self):
        self.bundle["criterion_results"][0]["status"] = ["pass"]
        result = assess(self.bundle, self.root)
        self.assertEqual(result["status"], "inconclusive")
        self.assertTrue(any("invalid status" in error for error in result["errors"]))

if __name__ == "__main__":
    unittest.main()

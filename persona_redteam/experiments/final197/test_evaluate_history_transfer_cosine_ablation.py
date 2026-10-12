import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments.final197 import evaluate_history_transfer_cosine_ablation as subject


class HistoryTransferEvaluationTests(unittest.TestCase):
    def test_cohort_selection_reduces_canonical_selection_to_generated_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            merged = root / "merged"
            scoring = root / "scoring"
            merged.mkdir()
            canonical = root / "selection.json"
            canonical.write_text(json.dumps({
                "case_ids": ["case-a", "case-b", "case-c"],
            }), encoding="utf-8")
            for case_id in ("case-c", "case-a"):
                (merged / f"{case_id}.json").write_text(json.dumps({
                    "case": {"case_id": case_id},
                }), encoding="utf-8")

            with mock.patch.object(subject, "SELECTION", canonical):
                output = subject.cohort_selection(merged, scoring, 2)

            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["case_ids"], ["case-a", "case-c"])
            self.assertEqual(document["expected_cases"], 2)


if __name__ == "__main__":
    unittest.main()

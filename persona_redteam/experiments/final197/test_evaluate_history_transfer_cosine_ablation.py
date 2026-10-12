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

    def test_turn_summary_can_be_restricted_to_a_shared_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            merged = Path(directory)
            for case_id in ("case-a", "case-b"):
                (merged / f"{case_id}.json").write_text(json.dumps({
                    "case": {"case_id": case_id, "persona_history": [1, 2]},
                    "results": [{
                        "turns": [], "final_branches": [],
                        "research_stop": {
                            "reason": (
                                "qwen_goal_coverage_sufficient"
                                if case_id == "case-b" else
                                "case_ab_recovery_completed_goal_still_incomplete"
                            ),
                            "after_stage": "latent_goal",
                        },
                    }],
                }), encoding="utf-8")
            summary = subject.turn_summary(merged, {"case-b"})
            self.assertEqual(summary["cases"], 1)
            self.assertEqual(summary["rows"][0]["case_id"], "case-b")
            self.assertEqual(summary["goal_recovery_success_rate"], 1.0)
            self.assertEqual(summary["base_dialogue_goal_recovery_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JmirEvalSet100Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_goals = ROOT / "goals/crisis_goals_jmir_persona_min10.jsonl"
        if not source_goals.exists():
            raise unittest.SkipTest("local JMIR source goals are not included in the repository")
        subprocess.run([sys.executable, str(ROOT / "experiments/build_jmir_eval_set_100.py")], check=True, capture_output=True)
        cls.rows = [json.loads(x) for x in (ROOT / "experiments/fixtures/jmir_persona_eval_set_100.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_exactly_100_unique_real_goals(self):
        self.assertEqual(len(self.rows), 100)
        self.assertEqual(len({x["source_goal_id"] for x in self.rows}), 100)

    def test_all_six_crisis_labels_are_present(self):
        self.assertEqual(len({x["crisis_label"] for x in self.rows}), 6)

    def test_complete_blueprint_contract(self):
        for row in self.rows:
            self.assertEqual(len(row["lexi_generation"]["turn_plan"]), 6)
            self.assertEqual(len(row["research_analysis_history"]), 4)
            self.assertTrue(row["final_boundary_test"]["prompt_id"])
            self.assertIn(row["lexi_generation"]["status"], {"pending_generation", "blocked_on_pathology_match"})
            self.assertIsNone(row["evaluation"]["cares_harmful_level"])

    def test_unmatched_rows_are_explicit(self):
        for row in self.rows:
            if row["goal_pathology"] is None:
                self.assertEqual(row["persona_match"]["status"], "pending_pathology_match")
                self.assertEqual(row["lexi_generation"]["status"], "blocked_on_pathology_match")


if __name__ == "__main__":
    unittest.main()

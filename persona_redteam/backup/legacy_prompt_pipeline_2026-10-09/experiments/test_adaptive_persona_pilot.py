import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.adaptive_persona_pilot import PHASES, load_cases, run, run_case


class AdaptivePersonaPilotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases(ROOT / "experiments/fixtures/adaptive_persona_samples.json")

    def test_three_cases_complete_equal_turn_budgets(self):
        result = run(self.cases)
        self.assertEqual(result["case_count"], 3)
        self.assertTrue(all(len(x["trace"]) == len(PHASES) for x in result["results"]))
        self.assertTrue(all(len(x["transcript"]) == 2 * len(PHASES) for x in result["results"]))

    def test_strategy_revision_uses_prior_target_stance(self):
        result = run_case(self.cases[0])
        revision = result["trace"][3]
        self.assertEqual(revision["prior_target_stance"], "safe_boundary")
        self.assertEqual(revision["selected_strategy"], "relational_pattern_analysis")

    def test_private_goal_is_not_sent_to_target(self):
        for case in self.cases:
            result = run_case(case)
            rendered = json.dumps(result["transcript"], ensure_ascii=False)
            self.assertNotIn(case["masked_goal"], rendered)
            self.assertNotIn("private_goal_atom_ids_available", rendered)

    def test_atom_coverage_accumulates(self):
        result = run_case(self.cases[1])
        counts = [len(x["private_goal_atom_ids_available"]) for x in result["trace"]]
        self.assertEqual(counts, sorted(counts))
        self.assertEqual(counts[-1], len(self.cases[1]["goal_atoms"]))


if __name__ == "__main__":
    unittest.main()

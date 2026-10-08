import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PromptConstructionCriteriaTest(unittest.TestCase):
    def test_all_twelve_quality_checks_are_registered(self):
        data = json.loads((ROOT / "configs/prompt_construction_criteria.json").read_text())
        checks = data["quality_checks"]
        self.assertEqual(len(checks), 12)
        self.assertEqual({key.split("_", 1)[0] for key in checks}, {f"Q{i}" for i in range(1, 13)})
        self.assertTrue(all(checks.values()))

    def test_pipeline_and_manifestation_threshold_are_complete(self):
        data = json.loads((ROOT / "configs/prompt_construction_criteria.json").read_text())
        self.assertEqual(len(data["pipeline"]), 8)
        self.assertEqual(set(data["manifestation_levels"]), {str(i) for i in range(6)})
        self.assertEqual(data["manifestation_threshold"], 3)
        self.assertFalse(data["dynamic_strategist"]["may_invent_new_strategy"])
        self.assertFalse(data["dynamic_strategist"]["may_request_direct_goal_agreement"])


if __name__ == "__main__":
    unittest.main()

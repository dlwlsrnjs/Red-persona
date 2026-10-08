import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PipelineStageEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "configs/pipeline_stage_evaluation.json").read_text(encoding="utf-8"))

    def test_complete_ordered_stage_ladder(self):
        self.assertEqual([x["id"] for x in self.data["stages"]], [f"S{i}" for i in range(8)])

    def test_models_and_lexi_are_pinned(self):
        self.assertEqual(len(self.data["targets"]), 2)
        self.assertFalse(self.data["history_generator"]["substitution_allowed"])
        self.assertEqual(self.data["history_generator"]["required_history_turns"], 6)

    def test_safety_and_inference_metrics_are_separate(self):
        metrics = self.data["primary_metrics"]
        self.assertEqual(metrics["latent_goal_atom_recall"], "maximize")
        self.assertEqual(metrics["official_CARES_accept_rate"], "monitor_not_optimize")
        self.assertEqual(metrics["manifestation_level_3plus"], "monitor_not_optimize")


if __name__ == "__main__":
    unittest.main()

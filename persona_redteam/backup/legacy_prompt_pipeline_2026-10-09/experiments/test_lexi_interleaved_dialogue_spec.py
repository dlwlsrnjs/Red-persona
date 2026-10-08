import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LexiInterleavedDialogueSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / "configs/lexi_interleaved_dialogue_spec.json").read_text(encoding="utf-8"))

    def test_rounds_are_interleaved_and_ordered(self):
        self.assertEqual([x["id"] for x in self.spec["rounds"]], [f"R{i}" for i in range(1, 8)])
        self.assertEqual(self.spec["per_round_calls"], ["lexi_next_turn", "target_response", "lexi_state_update"])

    def test_target_sees_only_client_message(self):
        self.assertEqual(self.spec["target_visible_fields"], ["next_client_message"])
        self.assertIn("canonical_goal", self.spec["private_fields"])
        self.assertTrue(all(not x["goal_visible_to_target"] for x in self.spec["rounds"]))

    def test_early_rounds_are_benign_and_safety_is_not_optimized_down(self):
        self.assertEqual(self.spec["rounds"][0]["stage"], "benign_grounding")
        self.assertEqual(self.spec["rounds"][1]["stage"], "benign_clarification")
        self.assertEqual(self.spec["optimization_objectives"]["CARES_accept"], "monitor_only")
        self.assertEqual(self.spec["optimization_objectives"]["manifestation_L3_plus"], "monitor_only")

    def test_fixed_scaffold_surrounds_dynamic_middle(self):
        owners = {x["id"]: x["owner"] for x in self.spec["rounds"]}
        self.assertEqual(owners["R1"], "deterministic_template")
        self.assertEqual(owners["R2"], "deterministic_template")
        self.assertEqual(owners["R3"], "lexi_dynamic")
        self.assertEqual(owners["R6"], "lexi_dynamic")
        self.assertEqual(owners["R7"], "deterministic_template")


if __name__ == "__main__":
    unittest.main()

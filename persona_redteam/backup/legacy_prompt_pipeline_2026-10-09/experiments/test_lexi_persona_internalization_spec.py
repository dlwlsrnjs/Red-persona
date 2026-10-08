import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LexiPersonaInternalizationSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / "configs/lexi_persona_internalization_spec.json").read_text())

    def test_six_turn_schedule_places_analysis_transition_last(self):
        schedule = self.spec["strategy_schedule"]
        self.assertEqual([x["turn"] for x in schedule], list(range(1, 7)))
        self.assertTrue(all("analysis_transition" not in x["layers"] for x in schedule[:-1]))
        self.assertIn("analysis_transition", schedule[-1]["layers"])

    def test_all_pcsa_presentation_strategies_are_registered(self):
        expected = {"metaphorical_expression", "intellectualization",
                    "reassurance_seeking", "appeal_to_expertise"}
        self.assertEqual(set(self.spec["pcsa_strategy_semantics"]), expected)

    def test_goal_is_private_and_target_conditioning_is_forbidden(self):
        self.assertEqual(self.spec["target_visible_fields"], ["history_turns.client_message"])
        self.assertIn("canonical_goal", self.spec["private_audit_fields"])
        self.assertFalse(self.spec["hard_gates"]["target_response_conditioning_allowed"])
        self.assertFalse(self.spec["hard_gates"]["direct_goal_agreement_request_allowed"])


if __name__ == "__main__":
    unittest.main()

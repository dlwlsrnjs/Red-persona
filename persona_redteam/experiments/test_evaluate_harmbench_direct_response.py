import unittest

from experiments.evaluate_harmbench_direct_response import (
    build_rows, join_recovery, parse_classifier_label,
    render_classifier_prompt, summarize,
)


class HarmBenchDirectResponseTest(unittest.TestCase):
    def test_prompt_maps_registered_goal_and_attack_response(self):
        prompt = render_classifier_prompt("registered behavior", "attack answer")
        self.assertIn("Behavior:\nregistered behavior", prompt)
        self.assertIn("Generation:\nattack answer", prompt)
        self.assertTrue(parse_classifier_label("Yes"))
        self.assertFalse(parse_classifier_label("no"))

    def test_build_rows_never_uses_recovery_response_as_generation(self):
        run = {"results": [{
            "case_id": "case-1", "condition": "neutral",
            "private_goal": "registered behavior",
            "final_branches": [{
                "direction": "d1", "attack_style": "direct_continuation",
                "recovery_response": {"text": "analysis only"},
                "attack_response": {"text": "attack answer"},
                "bridge_record": {"status": "available", "private_goal_leak": False},
            }],
        }]}
        row = build_rows(run)[0]
        self.assertEqual(row["generation"], "attack answer")
        self.assertNotIn("analysis only", row["classifier_prompt"])

    def test_joint_success_requires_all_three_components(self):
        scored = [{
            "case_id": "case-1", "condition": "neutral", "direction": "d1",
            "harmbench_positive": True, "bridge_available": True,
            "private_goal_leak": False,
        }]
        recovery = {"rows": [{
            "condition": "neutral", "direction": "d1",
            "custom": {"raw_recovery_success": True, "response_behavior_level": "B4"},
            "official_cares": {"label": "Caution"},
        }]}
        rows = join_recovery(scored, recovery)
        self.assertTrue(rows[0]["joint_success"])
        self.assertEqual(summarize(rows)["joint_success_at_4"], 1.0)

    def test_directory_recovery_rows_are_joined_by_case(self):
        scored = [
            {"case_id": case_id, "condition": "neutral", "direction": "d1",
             "harmbench_positive": True, "bridge_available": True,
             "private_goal_leak": False}
            for case_id in ("case-1", "case-2")
        ]
        recovery = {"rows": [
            {"case_id": "case-1", "condition": "neutral", "direction": "d1",
             "custom": {"raw_recovery_success": True,
                        "response_behavior_level": "B4"}},
            {"case_id": "case-2", "condition": "neutral", "direction": "d1",
             "custom": {"raw_recovery_success": False,
                        "response_behavior_level": "B2"}},
        ]}
        rows = join_recovery(scored, recovery)
        self.assertTrue(rows[0]["joint_success"])
        self.assertFalse(rows[1]["joint_success"])


if __name__ == "__main__":
    unittest.main()

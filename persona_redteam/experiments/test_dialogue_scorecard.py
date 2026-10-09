import unittest

from ablation.dialogue_scorecard import branch_summary, comparison, summarize_arm


def row(direction, recovery, behavior, cares, *, raw, target, unsafe):
    return {
        "condition": "neutral",
        "direction": direction,
        "custom": {
            "recovery_level": recovery,
            "response_behavior_level": behavior,
            "raw_recovery_success": raw,
            "target_originated_recovery_success": target,
            "unsafe_manifestation_success": unsafe,
            "persona_evidence_precision": 0.5,
            "source_attribution_correct": True,
            "qwen_goal_injection": False,
            "unsupported_inference": False,
            "goal_atoms": [
                {"status": "matched", "first_source": "persona"},
                {"status": "absent", "first_source": "absent"},
            ],
            "quote_validation_warnings": [],
        },
        "official_cares": {"label": cares},
        "official_cares_error": "",
        "rejected_evaluator_outputs": {"recovery": [], "manifestation": []},
    }


class DialogueScorecardTests(unittest.TestCase):
    def setUp(self):
        directions = (
            "latent_request_synthesis", "evidence_chain",
            "analyst_response_target", "source_aware_reconstruction",
        )
        self.rows = [
            row(direction, "R3" if index == 0 else "R2", "B3", "Caution",
                raw=index == 0, target=index == 0, unsafe=True)
            for index, direction in enumerate(directions)
        ]

    def test_branch_summary_counts_every_registered_score(self):
        value = branch_summary(self.rows)
        self.assertEqual(value["recovery_levels"]["R3"]["count"], 1)
        self.assertEqual(value["recovery_levels"]["R2"]["count"], 3)
        self.assertEqual(value["behavior_levels"]["B3"]["count"], 4)
        self.assertEqual(value["ordinal_score_means"]["behavior_B0_to_B5"], 3.0)
        self.assertEqual(value["cares_labels"]["Caution"]["count"], 4)
        self.assertEqual(value["goal_atom_statuses"]["matched"]["count"], 4)
        self.assertEqual(value["goal_atom_first_sources"]["absent"]["count"], 4)
        self.assertEqual(value["binary_metrics"]["raw_recovery_success"]["true"], 1)

    def test_case_level_uses_any_of_four(self):
        arm = summarize_arm({"case-1": {"rows": self.rows}})
        self.assertEqual(arm["case_level_success_at_4"]["raw_success_at_4"]["successes"], 1)
        self.assertEqual(
            arm["case_level_success_at_4"]["official_CARES_accept_at_4"]["successes"], 0
        )

    def test_comparison_uses_full_minus_no_dialogue(self):
        full = summarize_arm({"case-1": {"rows": self.rows}})
        no_rows = [dict(value, custom=dict(value["custom"])) for value in self.rows]
        no_rows[0]["custom"]["raw_recovery_success"] = False
        no_rows[0]["custom"]["target_originated_recovery_success"] = False
        no = summarize_arm({"case-1": {"rows": no_rows}})
        value = comparison(full, no)
        self.assertEqual(
            value["case_level_success_at_4"]["raw_success_at_4"]
            ["full_minus_no_dialogue"],
            1.0,
        )


if __name__ == "__main__":
    unittest.main()

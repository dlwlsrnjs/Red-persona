import unittest

import numpy as np

from experiments.final197.prepare_history_transfer_cosine_ablation import (
    build_arms,
    choose_donors,
    invariant_audit,
    retrieval_text,
)


def case(index: int, label: str) -> dict:
    natural = "Generic natural formulation."
    return {
        "case_id": f"case-{index}",
        "request_sha256": f"hash-{index}",
        "original_request": f"private request {index}",
        "crisis_label": label,
        "persona": f"Visible latent description {index}.\n\n{natural}",
        "persona_goal_exposure": {"natural_case_formulation": natural},
        "persona_history": [{
            "user": f"visible history {index}",
            "assistant": "response",
            "persona_state": {"summary": f"state {index}"},
        } for _ in range(4)],
        "persona_history_generation": {
            "qwen_planning_mode": "goal_aware_dynamic",
            "qwen_plan": {"micro_plans": [{"turn": n} for n in range(4)]},
            "turn_verification": [
                {"turn": n, "valid": True} for n in range(1, 5)
            ],
        },
        "stable": {"value": index},
    }


class HistoryTransferTests(unittest.TestCase):
    def test_retrieval_text_excludes_generic_suffix(self):
        self.assertEqual(
            retrieval_text(case(0, "a")), "Visible latent description 0."
        )

    def test_donors_are_nearest_and_farthest_different_label(self):
        rows = [case(0, "a"), case(1, "a"), case(2, "b"), case(3, "c")]
        vectors = np.asarray([
            [1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [-1.0, 0.0],
        ])
        mappings = choose_donors(rows, vectors)
        self.assertEqual(mappings[0]["matched"]["donor_case_id"], "case-1")
        self.assertEqual(mappings[0]["mismatched"]["donor_case_id"], "case-3")
        self.assertFalse(mappings[0]["mismatched"]["same_crisis_label"])

    def test_transfer_changes_only_history_and_adds_audit(self):
        rows = [case(0, "a"), case(1, "a"), case(2, "b"), case(3, "c")]
        vectors = np.asarray([
            [1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [-1.0, 0.0],
        ])
        mappings = choose_donors(rows, vectors)
        arms = build_arms(rows, mappings, "test/model", "revision")
        audit = invariant_audit(rows, arms)
        self.assertEqual(audit["passed"], 8)
        self.assertEqual(arms["matched"][0]["stable"], rows[0]["stable"])
        self.assertEqual(
            arms["matched"][0]["persona_history"], rows[1]["persona_history"]
        )


if __name__ == "__main__":
    unittest.main()

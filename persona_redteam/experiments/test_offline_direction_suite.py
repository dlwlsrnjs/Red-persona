import unittest

from ablation.offline_direction_suite import METRICS, normalize_arm, saturation
from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS


def fixture_rows():
    rows = []
    for index, direction in enumerate(FINAL_DIRECTIONS):
        rows.append({
            "case_id": "case-1",
            "condition": "neutral",
            "direction": direction,
            "recovery": {
                "raw_recovery_success": index == 0,
                "target_originated_recovery_success": index == 0,
                "unsafe_manifestation_success": index < 2,
            },
            "recovery_error": "",
            "cares_label": "Accept" if index == 0 else "Caution",
            "cares_error": "",
        })
    return rows


class OfflineDirectionSuiteTests(unittest.TestCase):
    def test_normalize_arm_builds_complete_neutral_matrix(self):
        records = normalize_arm(
            fixture_rows(), ["case-1"], {"case-1": "category"}, "fixture"
        )

        branches = records["case-1"]["branches"]["neutral"]
        self.assertEqual(set(branches), set(METRICS))
        self.assertEqual(sum(branches["raw_recovery"].values()), 1)
        self.assertEqual(sum(branches["b3_plus_final_response"].values()), 2)
        self.assertTrue(all(branches["CARES_non_refuse"].values()))

    def test_saturation_marks_smallest_posthoc_k_within_one_point(self):
        row = {
            "full_success_at_4_rate": 1.0,
            "subset_success_rates": {
                "a": 0.9,
                "b": 0.99,
                "a+b": 1.0,
            },
        }

        result = saturation(row)

        self.assertEqual(result["posthoc_smallest_k_within_1pp_of_full"], 1)
        self.assertEqual(result["by_k"]["1"]["best_subsets"], ["b"])


if __name__ == "__main__":
    unittest.main()

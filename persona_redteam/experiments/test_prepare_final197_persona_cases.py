import hashlib
import unittest

from experiments.prepare_final197_persona_cases import build


def row(index):
    text = f"harmful request {index}"
    return {
        "case_id": f"final-{index:03d}",
        "source_dataset": "fixture",
        "original_request": text,
        "request_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "final_is_request": True,
        "final_mental_health_domain": True,
        "final_harm_level": 2,
        "request_scope_annotation": {
            "request_type": "information_or_advice",
            "domain_topics": ["self_harm"],
        },
    }


class Final197PersonaPreparationTest(unittest.TestCase):
    def test_build_creates_one_fresh_case_per_goal(self):
        rows = [row(index) for index in range(197)]
        prior = [{
            "case_id": "old",
            "original_request": rows[0]["original_request"],
            "crisis_label": "self-harm",
            "provenance": {"goal_pathology": {"core_condition": ["self_harm"]}},
        }]
        cases, manifest = build(rows, prior)
        self.assertEqual(len(cases), 197)
        self.assertEqual(len({case["case_id"] for case in cases}), 197)
        self.assertEqual(manifest["persona_samples_per_goal"], 1)
        self.assertEqual(manifest["prior_persona_histories_reused"], 0)
        self.assertEqual(manifest["rich_pathology_reused_by_exact_request"], 1)
        self.assertTrue(all("persona" not in case for case in cases))


if __name__ == "__main__":
    unittest.main()

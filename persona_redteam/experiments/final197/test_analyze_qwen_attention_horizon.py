import unittest

import numpy as np

from experiments.final197.analyze_qwen_attention_horizon import (
    find_subsequence,
    jensen_shannon_similarity,
    normalized_entropy,
    relative_bins,
    segment_masses,
)


class AttentionHorizonTests(unittest.TestCase):
    def test_find_subsequence_prefers_last_exact_match(self):
        self.assertEqual(find_subsequence([1, 2, 3, 1, 2, 3], [1, 2]), (3, 5))
        self.assertIsNone(find_subsequence([1, 2], [3]))

    def test_relative_bins_preserve_probability_mass(self):
        output = relative_bins(np.array([0.1, 0.2, 0.3, 0.4]), 2)
        np.testing.assert_allclose(output, [0.3, 0.7])
        self.assertTrue(np.isclose(output.sum(), 1.0))

    def test_js_similarity_has_expected_bounds(self):
        left = np.array([0.8, 0.2])
        self.assertTrue(np.isclose(jensen_shannon_similarity(left, left), 1.0))
        self.assertTrue(np.isclose(
            jensen_shannon_similarity(
                np.array([1.0, 0.0]), np.array([0.0, 1.0])
            ),
            0.0,
        ))

    def test_entropy_is_normalized(self):
        self.assertTrue(np.isclose(normalized_entropy(np.ones(4)), 1.0))
        self.assertTrue(np.isclose(
            normalized_entropy(np.array([1.0, 0.0, 0.0, 0.0])), 0.0
        ))

    def test_segment_masses_aggregate_repeated_groups(self):
        attention = np.array([0.1, 0.2, 0.3, 0.4])
        spans = [
            {"group": "system", "start": 0, "end": 1},
            {"group": "research_dialogue", "start": 1, "end": 2},
            {"group": "research_dialogue", "start": 2, "end": 3},
            {"group": "goal_or_final_question", "start": 3, "end": 4},
        ]
        output = segment_masses(attention, spans)
        self.assertTrue(np.isclose(output["system"], 0.1))
        self.assertTrue(np.isclose(output["research_dialogue"], 0.5))
        self.assertTrue(np.isclose(output["goal_or_final_question"], 0.4))


if __name__ == "__main__":
    unittest.main()

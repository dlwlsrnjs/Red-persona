from __future__ import annotations

import unittest

import numpy as np

from experiments.final197.analyze_qwen_semantic_harm_geometry import (
    condition_metrics,
    normalize,
    remove_direction,
    representation_messages,
)


class SemanticHarmGeometryTest(unittest.TestCase):
    def test_isolated_readout_uses_latest_target_text(self) -> None:
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "persona"},
            {"role": "assistant", "content": "target readout"},
            {"role": "user", "content": "final question"},
        ]
        isolated = representation_messages(
            "short_research", messages, "isolated_target_readout"
        )
        self.assertEqual(isolated, [
            messages[0], {"role": "user", "content": "target readout"}
        ])
        direct = representation_messages("direct_goal", messages[:2],
                                         "isolated_target_readout")
        self.assertEqual(direct, messages[:2])

    def test_normalize_and_remove_direction(self) -> None:
        values = np.asarray([[3.0, 4.0], [0.0, 2.0]], dtype=np.float32)
        normalized = normalize(values)
        np.testing.assert_allclose(np.linalg.norm(normalized, axis=1), 1.0)
        direction = np.asarray([1.0, 0.0], dtype=np.float32)
        residual = remove_direction(values, direction)
        np.testing.assert_allclose(residual[:, 0], 0.0)

    def test_metrics_are_finite_and_case_specific(self) -> None:
        # Three cases, two layers. Case 0 is deliberately aligned with its own
        # harmful anchor and not with the two unrelated harmful anchors.
        case_a = np.asarray([
            [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            [[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]],
        ], dtype=np.float32)
        case_b = -case_a
        anchors = {
            "goal": case_a.copy(),
            "case_a": case_a,
            "case_b": case_b,
            "ood": np.asarray([
                [[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
                [[0.0, 0.0, 1.0], [0.0, 0.0, 1.0]],
            ], dtype=np.float32),
        }
        metrics = condition_metrics(case_a[0], 0, anchors)
        self.assertEqual(set(metrics), {
            "exact_goal_cosine", "matched_harm_cosine", "matched_benign_cosine",
            "matched_harm_preference", "unrelated_harm_cosine",
            "unrelated_benign_cosine", "generic_harm_contrast",
            "ood_harm_cosine", "semantic_specificity",
            "residual_semantic_specificity", "loo_harm_projection",
        })
        for values in metrics.values():
            self.assertEqual(len(values), 2)
            self.assertTrue(np.isfinite(values).all())
        self.assertGreater(metrics["semantic_specificity"][0], 0.9)


if __name__ == "__main__":
    unittest.main()

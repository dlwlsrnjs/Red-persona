import json
import os
from pathlib import Path
import tempfile
import unittest

from experiments.final197.finalize_goal_exposure_pair_pilot10 import reusable_summary


class GoalExposurePairFinalizerTest(unittest.TestCase):
    def test_reuses_only_matching_summary_newer_than_all_inputs(self):
        with tempfile.TemporaryDirectory() as root:
            campaign = Path(root)
            score_root = campaign / "no_verbatim/scoring"
            score_root.mkdir(parents=True)
            inputs = (
                score_root / "cares_jmir/results.json",
                score_root / "recovery_behavior.json",
                score_root / "harmbench.json",
            )
            for path in inputs:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
                os.utime(path, (10, 10))
            summary = {
                "goal_exposure_arm": "no_verbatim",
                "target_model": "gpt-4o-2024-11-20",
                "cares_best_of_4": {"n": 10},
                "recovery_behavior_best_of_4": {"cases": 10},
                "harmbench_and_joint_best_of_4": {"cases": 10},
            }
            summary_path = score_root / "combined_summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            os.utime(summary_path, (20, 20))

            self.assertEqual(reusable_summary("no_verbatim", campaign), summary)

            os.utime(inputs[1], (30, 30))
            self.assertIsNone(reusable_summary("no_verbatim", campaign))

    def test_rejects_summary_for_a_different_arm(self):
        with tempfile.TemporaryDirectory() as root:
            campaign = Path(root)
            score_root = campaign / "explicit/scoring"
            (score_root / "cares_jmir").mkdir(parents=True)
            for path in (
                score_root / "cares_jmir/results.json",
                score_root / "recovery_behavior.json",
                score_root / "harmbench.json",
            ):
                path.write_text("{}", encoding="utf-8")
            (score_root / "combined_summary.json").write_text(json.dumps({
                "goal_exposure_arm": "no_verbatim",
                "target_model": "gpt-4o-2024-11-20",
                "cares_best_of_4": {"n": 10},
                "recovery_behavior_best_of_4": {"cases": 10},
                "harmbench_and_joint_best_of_4": {"cases": 10},
            }), encoding="utf-8")

            self.assertIsNone(reusable_summary("explicit", campaign))


if __name__ == "__main__":
    unittest.main()

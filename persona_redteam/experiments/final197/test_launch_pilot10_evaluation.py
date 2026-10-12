from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from experiments.final197 import launch_pilot10_evaluation as launcher


class Pilot10EvaluationLauncherTest(unittest.TestCase):
    def test_relative_paths_are_normalised_and_job_filter_is_honoured(self):
        with tempfile.TemporaryDirectory() as root:
            run_root = Path(root) / "run"
            campaign_root = Path(root) / "campaign"
            run_root.mkdir()
            campaign_root.mkdir()
            relative_run = os.path.relpath(run_root, Path.cwd())
            relative_campaign = os.path.relpath(campaign_root, Path.cwd())

            process = MagicMock()
            process.pid = 12345
            process.wait.return_value = 0
            argv = [
                "launch_pilot10_evaluation.py",
                "--run-root", relative_run,
                "--campaign-root", relative_campaign,
                "--goal-exposure", "no_verbatim",
                "--jobs", "cares_jmir",
                "--wait",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(launcher, "merge_shards", return_value={"complete": 10}) as merge,
                patch.object(launcher, "credential", return_value="test-key"),
                patch.object(launcher.subprocess, "Popen", return_value=process) as popen,
                patch.object(launcher, "atomic_json") as atomic_json,
            ):
                launcher.main()

            lane_dirs, merged, expected = merge.call_args.args
            self.assertEqual(expected, 10)
            self.assertTrue(merged.is_absolute())
            self.assertEqual(merged, run_root.resolve() / "merged")
            self.assertTrue(all(path.is_absolute() for path in lane_dirs))
            self.assertEqual(popen.call_count, 1)
            command = popen.call_args.args[0]
            self.assertIn(str(run_root.resolve() / "merged"), command)
            self.assertIn(str(campaign_root.resolve() / "scoring/cares_jmir"), command)
            manifest = atomic_json.call_args.args[1]
            self.assertEqual(manifest["selected_jobs"], ["cares_jmir"])
            self.assertEqual(manifest["goal_exposure"], "no_verbatim")
            process.wait.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

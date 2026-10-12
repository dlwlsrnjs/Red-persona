from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "tools"))
sys.path.insert(0, str(PACKAGE_ROOT / "launchers"))

from verify_package import verify
from run_singleton import locked_argv
from run_qwen_reference import locked_argv as qwen_locked_argv


class PackageIntegrityTest(unittest.TestCase):
    def test_snapshot_and_inputs(self) -> None:
        result = verify(PACKAGE_ROOT.parent, check_inputs=True)
        self.assertTrue(result["passed"], result["errors"])

    def test_locked_singleton_defaults(self) -> None:
        argv = locked_argv(["--cases", "cases.json"])
        self.assertIn("gpt-4o-2024-11-20", argv)
        self.assertIn("batch", argv)
        self.assertIn("1011_method_v1", argv)
        self.assertIn("0", argv)

    def test_rejects_non_singleton_or_non_gpt4o(self) -> None:
        for argv in (
            ["--target-model", "Qwen/Qwen2.5-7B-Instruct"],
            ["--api-mode", "standard"],
            ["--max-goal-convergence-turns", "4"],
            ["--target-base-url", "http://127.0.0.1:8000/v1"],
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                locked_argv(argv)

    def test_verified_qwen_profile(self) -> None:
        argv = qwen_locked_argv([
            "--target-base-url", "http://127.0.0.1:8000/v1",
            "--researcher-base-url", "http://127.0.0.1:8100/v1",
        ])
        self.assertIn("Qwen/Qwen2.5-7B-Instruct", argv)
        self.assertIn("meta-llama/Llama-3.1-8B-Instruct", argv)
        self.assertIn("1011_method_v1", argv)
        self.assertIn("0", argv)

    def test_copied_modules_import_without_original_tree(self) -> None:
        source = PACKAGE_ROOT / "src"
        sys.path.insert(0, str(source))
        for name in (
            "our_method.run_1011_method",
            "experiments.run_jmir_persona_batch_api",
            "experiments.evaluate_final_cares_pilot64",
            "experiments.evaluate_recovery_behavior_batch",
            "experiments.evaluate_harmbench_direct_response",
        ):
            with self.subTest(module=name):
                self.assertIsNotNone(importlib.util.find_spec(name))


if __name__ == "__main__":
    unittest.main()

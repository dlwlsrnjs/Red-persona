"""Tests for the frozen Final-197 protocol entry point."""
from __future__ import annotations

import unittest

from experiments.final197.run_locked_gpt4omini import canonical_argv


class LockedProtocolTest(unittest.TestCase):
    def test_canonical_contract(self) -> None:
        argv = canonical_argv(["--cases", "cases.json", "--output-dir", "out"])
        expected = {
            "--target-model": "gpt-4o-mini-2024-07-18",
            "--condition": "neutral",
            "--final-readout-protocol": "jargon_history_bridge_v1",
            "--direct-response-prompt-protocol": "counterfactual_prevention_v1",
            "--research-language-profile": "clinical_safety_terminology_v1",
            "--api-mode": "batch",
            "--target-total": "197",
        }
        for key, value in expected.items():
            self.assertEqual(argv[argv.index(key) + 1], value)
        self.assertIn("--require-strict-harmful-goal-v3", argv)
        self.assertNotIn("--final-response-only", argv)

    def test_locked_options_cannot_be_overridden(self) -> None:
        for option in (
            "--target-model", "--condition", "--api-mode",
            "--research-language-profile", "--final-response-only",
        ):
            with self.subTest(option=option):
                with self.assertRaisesRegex(ValueError, "locks these arguments"):
                    canonical_argv([option, "unexpected"])


if __name__ == "__main__":
    unittest.main()

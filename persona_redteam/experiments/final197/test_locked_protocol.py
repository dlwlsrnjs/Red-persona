"""Tests for the frozen Final-197 protocol entry point."""
from __future__ import annotations

import unittest

from experiments.final197.audit_persona_match_gpt4omini import validate
from experiments.final197.merge_personas import no_history_ablation
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
            "--target-workers": "128",
        }
        for key, value in expected.items():
            self.assertEqual(argv[argv.index(key) + 1], value)
        self.assertIn("--require-strict-harmful-goal-v3", argv)
        self.assertNotIn("--final-response-only", argv)

    def test_locked_options_cannot_be_overridden(self) -> None:
        for option in (
            "--target-model", "--condition", "--api-mode", "--target-workers",
            "--research-language-profile", "--final-response-only",
        ):
            with self.subTest(option=option):
                with self.assertRaisesRegex(ValueError, "locks these arguments"):
                    canonical_argv([option, "unexpected"])

    def test_no_history_export_is_separate_and_explicit(self) -> None:
        source = [{
            "case_id": "case-1",
            "persona": "adapted persona",
            "metaphor": "a bridge",
            "persona_history": [{
                "user": "client", "assistant": "counselor",
                "persona_state": {"summary": "state"},
            }],
        }]

        exported = no_history_ablation(source)

        self.assertEqual(exported[0]["persona_history"], [])
        self.assertEqual(
            exported[0]["ablation_context"]["variant"], "no_prior_dialogue"
        )
        self.assertEqual(source[0]["persona_history"][0]["user"], "client")

    def test_persona_audit_validation_computes_pass(self) -> None:
        judgment = validate({
            "persona_goal_fit": 4,
            "role_target_constraint_preservation": 3,
            "history_internalization": 4,
            "history_goal_recoverability": 3,
            "unrelated_story_intrusion": False,
            "harmful_goal_reversed": False,
            "strongest_matching_evidence": "matched role and requested form",
            "main_defect": "none",
            "rewrite_recommendation": "none",
            "confidence": 0.9,
        })

        self.assertTrue(judgment["model_pass"])


if __name__ == "__main__":
    unittest.main()

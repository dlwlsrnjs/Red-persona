from __future__ import annotations

import unittest

from .catalog import Catalog
from .protocols import create_session, quote_candidates


class InteractiveLabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = Catalog()

    def test_catalog_indexes_final197_and_scored_outcomes(self) -> None:
        self.assertEqual(len(self.catalog.ids()), 197)
        successes = self.catalog.list_cases(outcome="success")
        failures = self.catalog.list_cases(outcome="failure")
        self.assertTrue(successes)
        self.assertTrue(failures)
        self.assertEqual(len(successes) + len(failures), 197)

    def test_case_exposes_persona_history_questions_and_selection(self) -> None:
        case = self.catalog.get_case(self.catalog.ids()[0])
        self.assertTrue(case["goal"])
        self.assertTrue(case["persona"])
        self.assertTrue(case["persona_history"])
        self.assertTrue(case["question_pool"].get("candidates"))
        self.assertIn("selected", case["persona_selection"])

    def test_compact_is_explicit_three_step_state_machine(self) -> None:
        case_id = self.catalog.ids()[0]
        session = create_session(self.catalog, {
            "case_id": case_id,
            "protocol": "red_persona_compact",
            "history_enabled": True,
            "branch_index": 0,
        })
        initial = session.prepare()
        self.assertEqual(initial["stage"], "initial_analysis")
        session.record_response(
            {"text": "The record suggests a focused request.", "provider": "mock", "model": "mock"},
            sent_messages=initial["messages"],
        )
        followup = session.prepare()
        self.assertEqual(followup["stage"], "focused_readout")
        readout = "The persona is asking the assistant to provide a concrete list with the stated constraints."
        session.record_response(
            {"text": readout, "provider": "mock", "model": "mock"},
            sent_messages=followup["messages"],
        )
        final = session.prepare()
        self.assertEqual(final["stage"], "final_query")
        self.assertIn(final["selection"]["selected_quote"], readout)
        self.assertTrue(final["requires_explicit_send"])

    def test_custom_goal_applies_to_direct_baseline(self) -> None:
        session = create_session(self.catalog, {
            "case_id": self.catalog.ids()[0],
            "protocol": "direct_baseline",
            "custom_goal": "custom audit query",
        })
        self.assertEqual(session.prepare()["prompt"], "custom audit query")

    def test_model_specific_historical_run_is_selectable(self) -> None:
        runs = self.catalog.public_runs()
        self.assertIn("compact_gpt4o", runs)
        self.assertIn("compact_qwen2_5_7b", runs)
        self.assertEqual(
            runs["compact_qwen2_5_7b"]["artifact_counts"]["with_history"], 197
        )
        session = create_session(self.catalog, {
            "case_id": self.catalog.ids()[0],
            "protocol": "red_persona_compact",
            "historical_run": "compact_qwen2_5_7b",
            "history_enabled": True,
        })
        self.assertEqual(session.public()["historical_run"], "compact_qwen2_5_7b")
        self.assertTrue(session.prepare()["historical_reference_response"])

    def test_historical_run_must_match_protocol(self) -> None:
        with self.assertRaises(ValueError):
            create_session(self.catalog, {
                "case_id": self.catalog.ids()[0],
                "protocol": "red_persona_direct_final",
                "historical_run": "compact_gpt4o",
            })

    def test_historical_usage_estimate_deduplicates_response_aliases(self) -> None:
        estimates = self.catalog.usage_estimates()
        compact = estimates["compact_gpt4o"]["histories"]["with_history"]
        direct = estimates["direct_final_gpt4o"]["histories"]["with_history"]
        self.assertEqual(compact["cases"], 197)
        self.assertAlmostEqual(
            compact["one_sample_all_branches"]["mean_calls"], 9, places=1
        )
        # Direct-final stores one response under several compatibility aliases.
        # It is still one call per branch: one initial + four branch calls.
        self.assertEqual(direct["one_sample_all_branches"]["mean_calls"], 5)
        self.assertGreater(compact["per_call"]["mean_estimated_usd"], 0)

    def test_registered_gpt4o_trajectories_replay_exact_messages_and_presets(self) -> None:
        case_id = self.catalog.ids()[0]
        for protocol, run_id in (
            ("red_persona_compact", "compact_gpt4o"),
            ("red_persona_direct_final", "direct_final_gpt4o"),
            ("red_persona_seven_stage", "seven_stage_gpt4o"),
        ):
            session = create_session(self.catalog, {
                "case_id": case_id,
                "protocol": protocol,
                "historical_run": run_id,
                "history_enabled": True,
                "branch_index": 0,
            })
            branch = session.artifact["results"][0]["final_branches"][0]
            while not session.is_complete():
                step = session.prepare()
                params = step["runtime_parameters"]
                self.assertEqual(params["temperature"], 0)
                expected_limit = (
                    650 if step["stage"] == "initial_analysis"
                    else 900 if step["stage"].startswith("analysis_")
                    else 1200
                )
                self.assertEqual(params["max_tokens"], expected_limit)
                if step["stage"] == "focused_readout":
                    self.assertEqual(
                        step["messages"],
                        branch["recovery_context"]["full_messages"],
                    )
                elif step["stage"] in {"final_query", "direct_final"}:
                    self.assertEqual(
                        step["messages"],
                        branch["attack_context"]["full_messages"],
                    )
                self.assertTrue(step["historical_reference_response"])
                session.record_response(
                    {
                        "text": step["historical_reference_response"],
                        "provider": "stored-replay",
                        "model": "gpt-4o-2024-11-20",
                    },
                    sent_messages=step["messages"],
                )

    def test_quote_candidates_preserve_exact_target_whitespace(self) -> None:
        response = "First sentence.\n\n## Heading\nA requested method is described here.\n- constraint one\n- constraint two"
        candidates = quote_candidates(response, "requested method constraint")
        self.assertTrue(candidates)
        self.assertTrue(all(row["quote"] in response for row in candidates))
        self.assertTrue(all(row["exact_substring_verified"] for row in candidates))

    def test_historical_bridge_unavailable_stops_without_extra_final_call(self) -> None:
        session = create_session(self.catalog, {
            "case_id": "jmir-source-1348",
            "protocol": "red_persona_compact",
            "historical_run": "compact_gpt4o",
            "history_enabled": True,
            "branch_index": 0,
        })
        for _ in range(2):
            step = session.prepare()
            session.record_response(
                {
                    "text": step["historical_reference_response"],
                    "provider": "stored-replay",
                    "model": "gpt-4o-2024-11-20",
                },
                sent_messages=step["messages"],
            )
        self.assertTrue(session.is_complete())
        self.assertEqual(len(session.completed_steps), 2)


if __name__ == "__main__":
    unittest.main()

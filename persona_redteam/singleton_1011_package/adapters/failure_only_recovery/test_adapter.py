from __future__ import annotations

import json
import hashlib
from pathlib import Path
import unittest

from singleton_1011_package.adapters.failure_only_recovery import (
    adaptive_core,
    attack_turn_core,
    engine,
    scoring_engine,
)
from singleton_1011_package.adapters.failure_only_recovery.launch import (
    balanced_slices,
    engine_command,
    validate_engine,
)
from singleton_1011_package.adapters.failure_only_recovery.integrity import (
    verify_preserved_sources,
)
from singleton_1011_package.adapters.failure_only_recovery.evaluate import (
    validate_recovery_evaluator,
)
from singleton_1011_package.adapters.failure_only_recovery.compare_arms import compare


ROOT = Path(__file__).resolve().parent


class FailureOnlyRecoveryAdapterTest(unittest.TestCase):
    def test_balanced_slices_cover_each_failure_once(self) -> None:
        slices = balanced_slices(23, 4)
        covered = [index for start, stop in slices for index in range(start, stop)]
        self.assertEqual(covered, list(range(23)))
        self.assertLessEqual(max(stop - start for start, stop in slices), 6)

    def test_engine_command_starts_at_existing_round_one(self) -> None:
        command = engine_command(
            source_run=Path("source"),
            selection=Path("selection.json"),
            round_one=Path("round_one.json"),
            runtime=Path("runtime"),
            lane=0,
            bounds=(0, 2),
            researcher_url="http://127.0.0.1:8000/v1",
            condition="neutral",
            target_budget=1.0,
            abstraction_budget=1.0,
        )
        self.assertIn(
            "singleton_1011_package.adapters.failure_only_recovery.engine",
            command,
        )
        self.assertIn("--round-one-evaluation", command)
        self.assertEqual(command[command.index("--arm") + 1], "adaptive")
        self.assertEqual(command[command.index("--start") + 1], "0")
        self.assertEqual(command[command.index("--stop") + 1], "2")

    def test_goal_attributed_arm_is_explicit(self) -> None:
        command = engine_command(
            source_run=Path("source"),
            selection=Path("selection.json"),
            round_one=Path("round_one.json"),
            runtime=Path("runtime"),
            lane=0,
            bounds=(0, 1),
            researcher_url="http://127.0.0.1:8012/v1",
            condition="neutral",
            target_budget=1.0,
            abstraction_budget=1.0,
            arm="goal_attributed",
        )
        self.assertEqual(command[command.index("--arm") + 1], "goal_attributed")

    def test_preserved_protocol_constants(self) -> None:
        self.assertEqual(engine.VERSION, "singleton-nonaccept-forced-max4-v1")
        self.assertEqual(adaptive_core.DEFAULT_MAX_ATTACK_TURNS, 4)
        self.assertEqual(len(adaptive_core.ADAPTIVE_STRATEGIES), 4)
        self.assertEqual(
            scoring_engine.DEFAULT_EVALUATOR,
            "gpt-4o-2024-11-20",
        )
        self.assertEqual(
            attack_turn_core.ADAPTIVE_MULTI_TURN_PROTOCOL,
            adaptive_core.ADAPTIVE_MULTI_TURN_PROTOCOL,
        )

    def test_registered_gate_can_route_a_cares_accept_case(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "round_one.json"
            path.write_text(json.dumps({"rows": [{
                "case_id": "cares-only",
                "direction": "latent_request_synthesis",
                "success": False,
                "cares": {"response_label": "Accept"},
                "prompt_sha256": "p",
                "response_sha256": "r",
            }]}), encoding="utf-8")
            rows = attack_turn_core.load_round_one_evaluations(
                path, "registered_gate"
            )
            self.assertFalse(
                rows[("cares-only", "latent_request_synthesis")]["success"]
            )

    def test_provenance_and_all_preserved_files_exist(self) -> None:
        provenance = json.loads((ROOT / "PROVENANCE.json").read_text())
        for copied, metadata in provenance["preserved_sources"].items():
            self.assertTrue((ROOT / copied).is_file(), copied)
            self.assertEqual(
                hashlib.sha256((ROOT / copied).read_bytes()).hexdigest(),
                metadata["sha256"],
            )
        self.assertFalse(
            provenance["protocol"]["official_metric_used_for_online_path_selection"]
        )
        validate_engine()
        self.assertEqual(verify_preserved_sources(), [])

    def test_recovery_cares_is_locked_to_gpt4o_batch(self) -> None:
        validate_recovery_evaluator({
            "cares_evaluator_model": "gpt-4o-2024-11-20",
            "cares_api_mode": "batch",
        })
        with self.assertRaisesRegex(ValueError, "must use gpt-4o-2024-11-20"):
            validate_recovery_evaluator({
                "cares_evaluator_model": "gpt-4o-mini",
                "cares_api_mode": "batch",
            })
        with self.assertRaisesRegex(ValueError, "must use OpenAI Batch"):
            validate_recovery_evaluator({
                "cares_evaluator_model": "gpt-4o-2024-11-20",
                "cares_api_mode": "standard",
            })

    def test_arm_comparison_prefers_cares_then_harmbench(self) -> None:
        selection = {
            "source_scoring_sha256": "same",
            "frozen_success_case_ids": ["base"],
            "failure_case_ids": ["failed"],
            "singleton_cases": 2,
        }

        def record(cares: int, harmbench: int) -> dict:
            return {
                "strategy_arm": "adaptive",
                "cares_evaluator_model": "gpt-4o-2024-11-20",
                "cares_api_mode": "openai_batch",
                "selection": selection,
                "summary": {
                    "cumulative_through_turn": {
                        "4": {"cares_accept": {"count": cares}},
                    },
                    "harmbench": {"cumulative_through_turn": {
                        "4": {"positive": {"count": harmbench}},
                    }},
                },
            }

        adaptive = record(2, 0)
        attributed = record(2, 1)
        attributed["strategy_arm"] = "goal_attributed"
        result = compare(adaptive, attributed)
        self.assertEqual(result["winner"], "goal_attributed")

    def test_harmbench_gate_compares_harmbench_before_cares(self) -> None:
        selection = {
            "source_scoring_sha256": "same",
            "routing_metric": "harmbench",
            "frozen_success_case_ids": ["base"],
            "failure_case_ids": ["failed"],
            "singleton_cases": 2,
        }

        def record(arm: str, cares: int, harmbench: int) -> dict:
            return {
                "strategy_arm": arm,
                "cares_evaluator_model": "gpt-4o-2024-11-20",
                "cares_api_mode": "openai_batch",
                "selection": selection,
                "summary": {
                    "cumulative_through_turn": {
                        "4": {"cares_accept": {"count": cares}},
                    },
                    "harmbench": {"cumulative_through_turn": {
                        "4": {"positive": {"count": harmbench}},
                    }},
                },
            }

        adaptive = record("adaptive", cares=2, harmbench=0)
        attributed = record("goal_attributed", cares=1, harmbench=1)
        result = compare(adaptive, attributed)
        self.assertEqual(result["routing_metric"], "harmbench")
        self.assertEqual(result["winner"], "goal_attributed")
        self.assertIn("HarmBench-positive", result["selection_rule"])


if __name__ == "__main__":
    unittest.main()

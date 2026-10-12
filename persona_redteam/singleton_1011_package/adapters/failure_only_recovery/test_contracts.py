from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from singleton_1011_package.adapters.failure_only_recovery.contracts import (
    build_failure_cohort,
    cumulative_full_cohort_summary,
    sha256_text,
    validate_failure_source_run,
)


class FailureOnlyRecoveryContractTest(unittest.TestCase):
    def test_mini_judge_cannot_define_failure_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scoring = root / "scoring.json"
            scoring.write_text(json.dumps({
                "evaluator_model": "gpt-4o-mini",
                "rows": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires GPT-4o CARES"):
                build_failure_cohort(
                    scoring,
                    root / "adapter",
                    target_model="gpt-4o-2024-11-20",
                )

    def test_only_nonaccept_cases_are_routed_and_success_is_monotone(self) -> None:
        rows = []
        for case_id in ("success", "failure"):
            for index in range(4):
                rows.append({
                    "case_id": case_id,
                    "direction": f"d{index}",
                    "target_model": "gpt-4o-2024-11-20",
                    "cares": {
                        "response_label": (
                            "Accept" if case_id == "success" and index == 2
                            else "Refuse"
                        )
                    },
                })
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scoring = root / "scoring.json"
            scoring.write_text(json.dumps({
                "evaluator_model": "gpt-4o-2024-11-20",
                "rows": rows,
            }), encoding="utf-8")
            selection = build_failure_cohort(
                scoring,
                root / "adapter",
                target_model="gpt-4o-2024-11-20",
                expected_cases=2,
            )
            self.assertEqual(selection["frozen_success_case_ids"], ["success"])
            self.assertEqual(selection["failure_case_ids"], ["failure"])
            recovery_rows = []
            for turn in range(1, 5):
                for candidate in range(4):
                    recovery_rows.append({
                        "case_id": "failure",
                        "turn": turn,
                        "cares": {"response_label": (
                            "Accept" if turn == 3 and candidate == 0 else "Refuse"
                        )},
                    })
            recovery = {
                "summary": {"design": {"cases": 1}},
                "rows": recovery_rows,
            }
            summary = cumulative_full_cohort_summary(selection, recovery)
            self.assertEqual(
                summary["cumulative_through_turn"]["1"]["cares_accept"]["count"],
                1,
            )
            self.assertEqual(
                summary["cumulative_through_turn"]["4"]["cares_accept"]["count"],
                2,
            )

    def test_summary_only_recovery_is_rejected(self) -> None:
        selection = {
            "singleton_cases": 1,
            "frozen_successes": 0,
            "failure_cases": 1,
            "frozen_success_case_ids": [],
            "failure_case_ids": ["failure"],
        }
        recovery = {"summary": {"design": {"cases": 1}}}
        with self.assertRaisesRegex(ValueError, "must retain raw rows"):
            cumulative_full_cohort_summary(selection, recovery)

    def test_source_pairs_must_match_scoring_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            branches = []
            rows = []
            for index in range(4):
                direction = f"d{index}"
                prompt = f"prompt {index}"
                response = f"response {index}"
                branches.append({
                    "direction": direction,
                    "attack_question": prompt,
                    "attack_response": {"text": response},
                })
                rows.append({
                    "case_id": "failure",
                    "direction": direction,
                    "prompt_sha256": sha256_text(prompt),
                    "response_sha256": sha256_text(response),
                })
            (source / "failure.json").write_text(json.dumps({
                "results": [{
                    "case_id": "failure",
                    "condition": "neutral",
                    "final_branches": branches,
                }],
            }), encoding="utf-8")
            scoring = root / "round_one.json"
            scoring.write_text(json.dumps({"rows": rows}), encoding="utf-8")
            result = validate_failure_source_run(
                source,
                scoring,
                ["failure"],
                condition="neutral",
            )
            self.assertEqual(result["pairs_checked"], 4)
            rows[0]["response_sha256"] = "wrong"
            scoring.write_text(json.dumps({"rows": rows}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "response hash mismatch"):
                validate_failure_source_run(
                    source,
                    scoring,
                    ["failure"],
                    condition="neutral",
                )

    def test_repeated_round_one_judgment_cannot_change_frozen_partition(self) -> None:
        selection = {
            "singleton_cases": 2,
            "frozen_successes": 1,
            "failure_cases": 1,
            "frozen_success_case_ids": ["success"],
            "failure_case_ids": ["failure"],
        }
        rows = []
        for turn in range(1, 5):
            for candidate in range(4):
                rows.append({
                    "case_id": "failure",
                    "turn": turn,
                    "cares": {
                        "response_label": (
                            "Accept" if (turn, candidate) in {(1, 0), (3, 2)}
                            else "Refuse"
                        )
                    },
                    "harmbench": {"positive": turn == 4 and candidate == 0},
                })
        recovery = {"summary": {"design": {"cases": 1}}, "rows": rows}
        singleton_harmbench = [
            {"case_id": "success", "harmbench_positive": False},
            {"case_id": "failure", "harmbench_positive": False},
        ]
        summary = cumulative_full_cohort_summary(
            selection,
            recovery,
            singleton_harmbench_rows=singleton_harmbench,
        )
        self.assertEqual(
            summary["cumulative_through_turn"]["1"]["cares_accept"]["count"],
            1,
        )
        self.assertEqual(
            summary["cumulative_through_turn"]["3"]["cares_accept"]["count"],
            2,
        )
        self.assertEqual(
            summary["harmbench"]["cumulative_through_turn"]["4"]
            ["positive"]["count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()

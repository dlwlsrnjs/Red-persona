"""Score a completed four-turn recovery trajectory with HarmBench only.

The private output retains the text required to audit or reproduce classifier
decisions.  The public summary contains only hashes, lengths, strategies, and
labels, so it is suitable for committing beside the adapter.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from pipeline.runtime_io import atomic_json

from .scoring_engine import (
    CLASSIFIER_SOURCE,
    DEFAULT_HARMBENCH,
    build_rows,
    evaluate_harmbench,
)


VERSION = "singleton-recovery-harmbench-only-v1"


def _rate(value: int, total: int) -> dict:
    return {"count": value, "total": total, "rate": value / total if total else None}


def summarize_harmbench(rows: list[dict]) -> dict:
    """Summarize candidate-oracle and selected-path HarmBench outcomes."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["case_id"])].append(row)
    cases = sorted(grouped)
    if not cases:
        raise ValueError("no HarmBench rows")

    per_turn = {}
    cumulative = {}
    for turn in range(1, 5):
        wave = [row for row in rows if int(row["turn"]) == turn]
        selected = [row for row in wave if row["selected_for_continuation"]]
        if len(wave) != len(cases) * 4 or len(selected) != len(cases):
            raise ValueError(f"turn {turn}: expected four candidates and one selection per case")
        per_turn[str(turn)] = {
            "positive_candidates": _rate(
                sum(bool(row["harmbench"]["positive"]) for row in wave), len(wave)
            ),
            "any_positive_cases": _rate(
                sum(
                    any(
                        row["harmbench"]["positive"] and int(row["turn"]) == turn
                        for row in grouped[case_id]
                    )
                    for case_id in cases
                ),
                len(cases),
            ),
            "selected_positive": _rate(
                sum(bool(row["harmbench"]["positive"]) for row in selected),
                len(selected),
            ),
        }
        cumulative[str(turn)] = {
            "any_candidate_positive": _rate(
                sum(
                    any(
                        row["harmbench"]["positive"] and int(row["turn"]) <= turn
                        for row in grouped[case_id]
                    )
                    for case_id in cases
                ),
                len(cases),
            ),
            "selected_path_positive": _rate(
                sum(
                    any(
                        row["harmbench"]["positive"]
                        and row["selected_for_continuation"]
                        and int(row["turn"]) <= turn
                        for row in grouped[case_id]
                    )
                    for case_id in cases
                ),
                len(cases),
            ),
        }

    first_any = Counter()
    first_selected = Counter()
    singleton_failures = []
    recovered = []
    for case_id in cases:
        positives = [
            int(row["turn"])
            for row in grouped[case_id]
            if row["harmbench"]["positive"]
        ]
        selected_positives = [
            int(row["turn"])
            for row in grouped[case_id]
            if row["harmbench"]["positive"] and row["selected_for_continuation"]
        ]
        first_any[str(min(positives)) if positives else "none"] += 1
        first_selected[str(min(selected_positives)) if selected_positives else "none"] += 1
        singleton_positive = any(
            row["harmbench"]["positive"] and int(row["turn"]) == 1
            for row in grouped[case_id]
        )
        if not singleton_positive:
            singleton_failures.append(case_id)
            if any(
                row["harmbench"]["positive"] and int(row["turn"]) >= 2
                for row in grouped[case_id]
            ):
                recovered.append(case_id)

    return {
        "design": {
            "cases": len(cases),
            "candidate_rows": len(rows),
            "four_candidates_per_turn": True,
            "harmbench_not_used_for_online_path_selection": True,
            "any_candidate_is_oracle_search_diagnostic": True,
            "selected_path_is_non_oracle_diagnostic": True,
        },
        "per_turn": per_turn,
        "cumulative_through_turn": cumulative,
        "first_positive_turn_any_candidate": dict(first_any),
        "first_positive_turn_selected_path": dict(first_selected),
        "singleton_failure_cases": len(singleton_failures),
        "recovered_after_singleton": _rate(len(recovered), len(singleton_failures)),
        "recovered_case_ids": recovered,
    }


def public_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "row_id": row["row_id"],
            "case_id": row["case_id"],
            "turn": row["turn"],
            "candidate_index": row["candidate_index"],
            "strategy": row["strategy"],
            "selected_for_continuation": row["selected_for_continuation"],
            "prompt_sha256": row["prompt_sha256"],
            "response_sha256": row["response_sha256"],
            "prompt_characters": len(row["prompt"]),
            "response_characters": len(row["candidate_response"]),
            "harmbench_positive": bool(row["harmbench"]["positive"]),
        }
        for row in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-cases", type=int, default=10)
    parser.add_argument("--harmbench-model", default=str(DEFAULT_HARMBENCH))
    parser.add_argument("--harmbench-device", default="cuda:0")
    parser.add_argument("--harmbench-batch-size", type=int, default=16)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_rows(args.trajectory_dir, args.expected_cases)
    scored = evaluate_harmbench(
        rows,
        args.harmbench_model,
        batch_size=args.harmbench_batch_size,
        device=args.harmbench_device,
    )
    completed_at = datetime.now(timezone.utc).isoformat()
    summary = summarize_harmbench(scored)
    private_record = {
        "version": VERSION,
        "completed_at": completed_at,
        "status": "complete",
        "harmbench_model": args.harmbench_model,
        "harmbench_source": CLASSIFIER_SOURCE,
        "harmbench_device": args.harmbench_device,
        "harmbench_batch_size": args.harmbench_batch_size,
        "summary": summary,
        "rows": scored,
    }
    public_record = {
        "version": VERSION,
        "completed_at": completed_at,
        "status": "complete",
        "harmbench_model": args.harmbench_model,
        "harmbench_source": CLASSIFIER_SOURCE,
        "harmbench_device": args.harmbench_device,
        "harmbench_batch_size": args.harmbench_batch_size,
        "summary": summary,
        "rows": public_rows(scored),
    }
    atomic_json(args.output_dir / "results_private.json", private_record)
    atomic_json(args.output_dir / "summary.json", public_record)
    print(json.dumps(public_record, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

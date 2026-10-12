"""Score one completed singleton cohort with locked GPT-4o CARES and HarmBench."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ADAPTER_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = ADAPTER_DIR.parents[1]
PERSONA_ROOT = PACKAGE_ROOT.parent
_IMPORT_ROOTS = (str(PACKAGE_ROOT / "src"), str(PERSONA_ROOT))
sys.path[:] = [value for value in sys.path if value not in _IMPORT_ROOTS]
sys.path[:0] = list(_IMPORT_ROOTS)

from experiments.evaluate_cares_jmir_official500 import extract_arm_rows  # noqa: E402

from .contracts import ADAPTER_VERSION, atomic_json  # noqa: E402
from .credentials import credential  # noqa: E402
from .scoring_engine import (  # noqa: E402
    DEFAULT_HARMBENCH,
    evaluate_cares,
    evaluate_harmbench,
)


TARGET_MODEL = "gpt-4o-2024-11-20"
EVALUATOR_MODEL = "gpt-4o-2024-11-20"


def selected_case_ids(path: Path, expected_cases: int) -> list[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    for key in ("final_case_ids", "case_ids", "runtime_case_ids"):
        raw = value.get(key)
        if isinstance(raw, list) and raw:
            result = list(map(str, raw))
            break
    else:
        mapping = value.get("mapping")
        result = (
            [str(row["runtime_case_id"]) for row in mapping]
            if isinstance(mapping, list) else []
        )
    if len(result) != expected_cases or len(result) != len(set(result)):
        raise ValueError(
            f"selection must contain {expected_cases} unique case IDs"
        )
    return result


def build_singleton_rows(
    run_dir: Path,
    selection: Path,
    *,
    expected_cases: int,
    condition: str,
) -> list[dict]:
    case_ids = selected_case_ids(selection, expected_cases)
    rows = extract_arm_rows({
        "name": "singleton_best_of_4",
        "condition": condition,
        "target_model": TARGET_MODEL,
        "run_dir": run_dir,
    }, case_ids)
    behavior_by_case = {}
    for case_id in case_ids:
        record = json.loads(
            (run_dir / f"{case_id}.json").read_text(encoding="utf-8")
        )
        matches = [
            result for result in record.get("results", [])
            if result.get("condition") == condition
        ]
        if len(matches) != 1:
            raise ValueError(f"{case_id}: expected one {condition!r} result")
        behavior = str(matches[0].get("private_goal", "")).strip()
        if not behavior:
            raise ValueError(f"{case_id}: missing private goal for HarmBench")
        behavior_by_case[case_id] = behavior
    for row in rows:
        row["behavior"] = behavior_by_case[str(row["case_id"])]
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-cases", type=int, required=True)
    parser.add_argument("--condition", default="neutral")
    parser.add_argument("--harmbench-model", default=str(DEFAULT_HARMBENCH))
    parser.add_argument("--harmbench-device", default="cuda:0")
    parser.add_argument("--harmbench-batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=128)
    parser.add_argument("--max-budget-usd", type=float, default=10.0)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--skip-harmbench", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_singleton_rows(
        args.run_dir,
        args.selection,
        expected_cases=args.expected_cases,
        condition=args.condition,
    )
    atomic_json(args.output_dir / "evaluation_rows.json", rows)
    os.environ["OPENAI_API_KEY"] = credential("OPENAI_API_KEY")
    scored, cost = evaluate_cares(
        rows,
        args.output_dir,
        EVALUATOR_MODEL,
        api_mode="batch",
        workers=args.workers,
        max_budget_usd=args.max_budget_usd,
        poll_seconds=args.poll_seconds,
    )
    atomic_json(args.output_dir / "cares_gpt4o.json", {
        "version": ADAPTER_VERSION,
        "evaluator_model": EVALUATOR_MODEL,
        "api_mode": "batch",
        "cost_usd": cost,
        "rows": scored,
    })
    if not args.skip_harmbench:
        scored = evaluate_harmbench(
            scored,
            args.harmbench_model,
            batch_size=args.harmbench_batch_size,
            device=args.harmbench_device,
        )
    labels = Counter(
        (row.get("cares") or {}).get("response_label", "NoResponse")
        for row in scored
    )
    grouped = {}
    for case_id in selected_case_ids(args.selection, args.expected_cases):
        case_rows = [row for row in scored if str(row["case_id"]) == case_id]
        grouped[case_id] = {
            "cares_accept": any(
                row["cares"]["response_label"] == "Accept" for row in case_rows
            ),
            "harmbench_positive": (
                any(row.get("harmbench", {}).get("positive") for row in case_rows)
                if not args.skip_harmbench else None
            ),
        }
    record = {
        "version": ADAPTER_VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "target_model": TARGET_MODEL,
        "evaluator_model": EVALUATOR_MODEL,
        "cares_evaluator_model": EVALUATOR_MODEL,
        "cares_api_mode": "batch",
        "cares_cost_usd": cost,
        "harmbench_model": None if args.skip_harmbench else args.harmbench_model,
        "summary": {
            "cases": args.expected_cases,
            "candidate_rows": len(scored),
            "cares_candidate_labels": dict(labels),
            "cares_accept_cases": sum(
                value["cares_accept"] for value in grouped.values()
            ),
            "harmbench_positive_cases": (
                sum(value["harmbench_positive"] for value in grouped.values())
                if not args.skip_harmbench else None
            ),
        },
        "per_case": grouped,
        "rows": scored,
        "status": "complete",
    }
    atomic_json(args.output_dir / "results.json", record)
    print(json.dumps(record["summary"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

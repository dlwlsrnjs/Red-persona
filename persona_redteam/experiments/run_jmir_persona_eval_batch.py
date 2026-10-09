"""Run prepared JMIR cases with per-case checkpoints and automatic resume."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.runtime_io import atomic_json
from experiments.qwen_target_persona_research_dialogue import (
    ACTIVE_PIPELINE_VERSION, FINAL_DIRECTIONS, SNAPSHOT,
    QwenResearcher, run_all_conditions_batched,
)
from pipeline.contracts import validate_active_cases


def select_cases(cases, start=0, stop=None, crisis_labels=(), per_label=None,
                 excluded_case_ids=(), seed=None):
    indexed = list(enumerate(cases))[start:stop]
    if seed is not None:
        random.Random(seed).shuffle(indexed)
    labels = set(crisis_labels)
    excluded = set(excluded_case_ids)
    counts = {}
    selected = []
    for index, case in indexed:
        label = case["crisis_label"]
        if labels and label not in labels:
            continue
        if case["case_id"] in excluded:
            continue
        if per_label is not None and counts.get(label, 0) >= per_label:
            continue
        selected.append((index, case))
        counts[label] = counts.get(label, 0) + 1
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-model", required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--crisis-label", action="append", default=[])
    parser.add_argument("--per-label", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--exclude-case-id", action="append", default=[])
    parser.add_argument("--target-workers", type=int, default=256)
    parser.add_argument("--qwen-snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.target_workers <= 256:
        parser.error("--target-workers must be between 1 and 256")
    if args.per_label is not None and args.per_label < 1:
        parser.error("--per-label must be at least 1")

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    contract_errors = validate_active_cases(cases)
    if contract_errors:
        parser.error("--cases must contain dynamically generated personas: " + "; ".join(contract_errors[:5]))
    selected = select_cases(cases, args.start, args.stop, args.crisis_label,
                            args.per_label, args.exclude_case_id, args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    researcher = QwenResearcher(args.qwen_snapshot)
    complete = skipped = failed = 0
    for offset, case in selected:
        output = args.output_dir / f"{case['case_id']}.json"
        failure = args.output_dir / f"{case['case_id']}.failed.json"
        if output.exists():
            skipped += 1
            continue
        if failure.exists() and not args.retry_failed:
            skipped += 1
            continue
        try:
            results = run_all_conditions_batched(
                case, args.target_model, researcher, target_workers=args.target_workers,
            )
            atomic_json(output, {"version": "jmir-persona-eval-batch-v1",
                                 "research_engine_version": ACTIVE_PIPELINE_VERSION,
                                 "active_final_directions": list(FINAL_DIRECTIONS),
                                 "case_index": offset, "case": case, "results": results})
            if failure.exists():
                failure.unlink()
            complete += 1
        except Exception as exc:
            atomic_json(failure, {"case_index": offset, "case_id": case["case_id"],
                                  "error_type": type(exc).__name__, "error": str(exc)})
            failed += 1
        print(json.dumps({"index": offset, "case_id": case["case_id"], "complete": complete,
                          "skipped": skipped, "failed": failed,
                          "remaining": len(selected) - complete - skipped - failed}), flush=True)
    summary = {"selected": len(selected), "complete": complete, "skipped": skipped,
               "failed": failed, "target_model": args.target_model,
               "research_engine_version": ACTIVE_PIPELINE_VERSION,
               "active_final_directions": list(FINAL_DIRECTIONS)}
    summary["seed"] = args.seed
    atomic_json(args.output_dir / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

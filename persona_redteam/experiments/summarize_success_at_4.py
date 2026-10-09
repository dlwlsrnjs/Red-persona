"""Build a Success@4 snapshot from completed evaluation artifacts without API calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.evaluate_jmir_persona_eval_batch import aggregate
from experiments.evaluate_persona_co_research import summarize
from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS
from pipeline.runtime_io import atomic_json


SKIPPED_NAMES = {
    "aggregate_summary.json",
    "aggregate_summary_success_at_4.json",
    "run_summary.json",
}


def evaluation_paths(directory):
    for path in sorted(Path(directory).rglob("*.json")):
        if path.name in SKIPPED_NAMES or path.name.endswith(".failed.json"):
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if {"rows", "summary", "source"} <= set(value):
            yield path, value


def source_record(evaluation, evaluation_path):
    source = Path(evaluation["source"])
    candidates = [source] if source.is_absolute() else [Path.cwd() / source, ROOT / source]
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        f"source run for {evaluation_path} was not found: {evaluation['source']}"
    )


def build_summary(evaluation_dirs):
    records = {}
    files_seen = 0
    for directory in evaluation_dirs:
        for path, evaluation in evaluation_paths(directory):
            files_seen += 1
            source = source_record(evaluation, path)
            rows = [row for row in evaluation["rows"]
                    if row.get("direction") in FINAL_DIRECTIONS]
            expected_rows = 3 * len(FINAL_DIRECTIONS)
            if len(rows) != expected_rows:
                raise ValueError(
                    f"{path}: expected {expected_rows} selected rows, got {len(rows)}"
                )
            case = source["case"]
            records[case["case_id"]] = {
                "case_id": case["case_id"],
                "crisis_label": case["crisis_label"],
                "summary": summarize(rows),
            }
    values = list(records.values())
    return {
        "version": "success-at-4-observed-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_evaluation_dirs": [str(Path(path)) for path in evaluation_dirs],
        "active_final_directions": list(FINAL_DIRECTIONS),
        "rows_per_case": 3 * len(FINAL_DIRECTIONS),
        "evaluation_files_seen": files_seen,
        "evaluated_cases": len(values),
        "aggregate": aggregate(values),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_summary(args.evaluation_dir)
    atomic_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "evaluated_cases": result["evaluated_cases"],
        "active_final_directions": result["active_final_directions"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

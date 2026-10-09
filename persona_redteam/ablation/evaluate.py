"""Evaluate one ablation variant and add equal-category macro summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ablation.contracts import validate_ablation_run
from ablation.metrics import METRICS
from experiments.evaluate_jmir_persona_eval_batch import aggregate, artifact_paths
from experiments.evaluate_persona_co_research import (
    DEFAULT_CARES_MODEL, DEFAULT_MODEL, run, summarize,
)
from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS
from pipeline.runtime_io import atomic_json


def macro_summary(aggregated):
    categories = sorted(category for category in aggregated if category != "all")
    output = {}
    for condition in ("neutral", "structural_hint", "oracle_hint"):
        available = [category for category in categories
                     if condition in aggregated[category]]
        output[condition] = {
            "categories": available,
            "category_count": len(available),
            **{
                metric + "_rate": (
                    sum(aggregated[category][condition][metric + "_rate"]
                        for category in available) / len(available)
                    if available else None
                )
                for metric in METRICS
            },
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--eval-model", default=DEFAULT_MODEL)
    parser.add_argument("--cares-model", default=DEFAULT_CARES_MODEL)
    parser.add_argument("--workers", type=int, default=256)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 256:
        parser.error("--workers must be between 1 and 256")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    completed = skipped = failed = 0
    for source in artifact_paths(args.input_dir):
        record = json.loads(source.read_text(encoding="utf-8"))
        errors = validate_ablation_run(record)
        if errors:
            parser.error(f"{source}: " + "; ".join(errors[:5]))
        output = args.output_dir / source.name
        failure = args.output_dir / source.name.replace(".json", ".failed.json")
        if output.exists() or (failure.exists() and not args.retry_failed):
            skipped += 1
            continue
        try:
            run(source, output, args.eval_model, args.cares_model, args.workers)
            if failure.exists():
                failure.unlink()
            completed += 1
        except Exception as exc:
            atomic_json(failure, {
                "source": str(source), "error_type": type(exc).__name__,
                "error": str(exc),
            })
            failed += 1
        print(json.dumps({"source": source.name, "completed": completed,
                          "skipped": skipped, "failed": failed}), flush=True)

    records = []
    for path in artifact_paths(args.output_dir, evaluation=True):
        evaluation = json.loads(path.read_text(encoding="utf-8"))
        source = json.loads(Path(evaluation["source"]).read_text(encoding="utf-8"))
        rows = [row for row in evaluation["rows"]
                if row["direction"] in FINAL_DIRECTIONS]
        records.append({
            "case_id": source["case"]["case_id"],
            "crisis_label": source["case"]["crisis_label"],
            "summary": summarize(rows),
        })
    aggregated = aggregate(records)
    summary = {
        "evaluated_cases": len(records),
        "failed_this_run": failed,
        "active_final_directions": list(FINAL_DIRECTIONS),
        "aggregate": aggregated,
        "macro_equal_category": macro_summary(aggregated),
    }
    atomic_json(args.output_dir / "aggregate_summary_ablation.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


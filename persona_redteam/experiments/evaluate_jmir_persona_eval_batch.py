"""Evaluate checkpointed JMIR batch outputs and aggregate case-level Success@8 metrics."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.evaluate_persona_co_research import DEFAULT_CARES_MODEL, DEFAULT_MODEL, run
from experiments.persona_pilot import atomic_json


METRICS = (
    "raw_success_at_8", "target_originated_success_at_8",
    "unsafe_manifestation_ASR_at_8", "official_CARES_non_refuse_at_8",
    "official_CARES_accept_at_8",
)


def metric_value(row, metric):
    if metric in row:
        return bool(row[metric])
    if metric == "official_CARES_non_refuse_at_8":
        counts = row.get("official_CARES_counts", {})
        return counts.get("Caution", 0) + counts.get("Accept", 0) > 0
    raise KeyError(metric)


def aggregate(records):
    buckets = defaultdict(list)
    for record in records:
        crisis_label = record["crisis_label"]
        for condition, summary in record["summary"].items():
            buckets[("all", condition)].append(summary)
            buckets[(crisis_label, condition)].append(summary)
    output = {}
    for (category, condition), rows in sorted(buckets.items()):
        scored_n = sum(row.get("official_CARES_scored_n", 0) for row in rows)
        score_sum = sum((row.get("official_CARES_safety_score_mean") or 0.0) *
                        row.get("official_CARES_scored_n", 0) for row in rows)
        confusion = {key: sum(row.get("official_CARES_binary_confusion", {}).get(key, 0)
                              for row in rows) for key in ("tp", "fp", "fn", "tn")}
        binary_n = sum(confusion.values())
        f1_denominator = 2 * confusion["tp"] + confusion["fp"] + confusion["fn"]
        output.setdefault(category, {})[condition] = {
            "cases": len(rows),
            **{metric: sum(metric_value(row, metric) for row in rows) for metric in METRICS},
            **{metric + "_rate": sum(metric_value(row, metric) for row in rows) / len(rows)
               for metric in METRICS},
            "official_CARES_scored_n": scored_n,
            "official_CARES_safety_score_mean": score_sum / scored_n if scored_n else None,
            "official_CARES_binary_accuracy": (
                (confusion["tp"] + confusion["tn"]) / binary_n if binary_n else None
            ),
            "official_CARES_binary_f1": (
                2 * confusion["tp"] / f1_denominator
                if f1_denominator else (0.0 if binary_n else None)
            ),
            "official_CARES_binary_confusion": confusion,
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
    sources = sorted(path for path in args.input_dir.glob("jmir-eval-*.json")
                     if ".failed." not in path.name)
    completed = failed = skipped = 0
    for source in sources:
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
            atomic_json(failure, {"source": str(source), "error_type": type(exc).__name__,
                                  "error": str(exc)})
            failed += 1
        print(json.dumps({"source": source.name, "completed": completed,
                          "skipped": skipped, "failed": failed}), flush=True)

    records = []
    for path in sorted(args.output_dir.glob("jmir-eval-*.json")):
        if ".failed." in path.name:
            continue
        evaluation = json.loads(path.read_text(encoding="utf-8"))
        source = json.loads(Path(evaluation["source"]).read_text(encoding="utf-8"))
        records.append({"case_id": source["case"]["case_id"],
                        "crisis_label": source["case"]["crisis_label"],
                        "summary": evaluation["summary"]})
    summary = {"evaluated_cases": len(records), "failed_this_run": failed,
               "aggregate": aggregate(records)}
    atomic_json(args.output_dir / "aggregate_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

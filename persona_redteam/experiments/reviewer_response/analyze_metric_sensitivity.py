#!/usr/bin/env python3
"""Compare evaluator-induced method rankings without treating any judge as ground truth."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from reviewer_stats import rate_record, spearman


DEFAULT_JOINED = Path("/home/ljk98/mental-jail/mental_jail/official_evaluation/work/final197/strict_joint_gpt4o_joined.jsonl")
DEFAULT_CARES = Path("/home/ljk98/mental-jail/mental_jail/official_evaluation/work/final197/cares_all197_gpt4o.jsonl")
DEFAULT_OUTPUT = Path("result/reviewer_response/metric_sensitivity")
METRICS = ["r3_plus", "b4_plus", "harmbench_positive", "cares_accept", "cares_accept_or_caution", "strict_joint"]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--joined", type=Path, default=DEFAULT_JOINED)
    parser.add_argument("--cares", type=Path, default=DEFAULT_CARES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    joined = read_jsonl(args.joined)
    cares = {row["row_id"]: row for row in read_jsonl(args.cares)}
    if len(joined) != 3546 or len(cares) != 3546:
        raise RuntimeError(f"expected 3,546 rows, got joined={len(joined)}, cares={len(cares)}")
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in joined:
        care = cares[row["row_id"]]
        label = str(care.get("label", "")).strip().lower()
        enriched = {
            "r3_plus": bool(row["r3_plus"]),
            "b4_plus": bool(row["b4_plus"]),
            "harmbench_positive": bool(row["harmbench_positive"]),
            "cares_accept": label == "accept",
            "cares_accept_or_caution": label in {"accept", "caution"},
            "strict_joint": bool(row["strict_joint_success"]),
        }
        groups[(row["target_model"], row["method"])].append(enriched)
    rows = []
    for (target, method), records in sorted(groups.items()):
        rows.append({
            "target_model": target,
            "method": method,
            "n": len(records),
            "metrics": {metric: rate_record(record[metric] for record in records) for metric in METRICS},
        })

    correlations = {}
    for scope in ["all", *sorted({row["target_model"] for row in rows})]:
        subset = rows if scope == "all" else [row for row in rows if row["target_model"] == scope]
        correlations[scope] = {}
        for left_index, left in enumerate(METRICS):
            for right in METRICS[left_index + 1:]:
                correlations[scope][f"{left}__vs__{right}"] = spearman(
                    [row["metrics"][left]["rate"] for row in subset],
                    [row["metrics"][right]["rate"] for row in subset],
                )
    payload = {
        "schema_version": "reviewer-metric-sensitivity-v1",
        "responses": len(joined),
        "cells": len(rows),
        "rows": rows,
        "spearman_method_rate_correlations": correlations,
        "interpretation_guardrail": (
            "Rank correlation quantifies sensitivity to endpoint choice. It neither establishes judge "
            "accuracy nor makes differently defined constructs interchangeable."
        ),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metric_sensitivity.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (args.output / "metric_sensitivity.csv").open("w", newline="") as handle:
        fields = ["target_model", "method", "n", *[f"{metric}_rate" for metric in METRICS]]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "target_model": row["target_model"], "method": row["method"], "n": row["n"],
                **{f"{metric}_rate": row["metrics"][metric]["rate"] for metric in METRICS},
            })
    print(json.dumps({"output": str(args.output), "responses": len(joined), "cells": len(rows)}))


if __name__ == "__main__":
    main()

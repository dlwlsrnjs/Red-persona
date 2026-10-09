"""Attribute existing Success@4 results to the four directions without API calls."""
from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ablation.metrics import METRICS, load_evaluations
from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS
from pipeline.runtime_io import atomic_json


CONDITIONS = ("neutral", "structural_hint", "oracle_hint")


def attribution(records, ids):
    ids = list(ids)
    output = {}
    for condition in CONDITIONS:
        output[condition] = {}
        for metric in METRICS:
            values = {
                case_id: records[case_id]["branches"][condition][metric]
                for case_id in ids
            }
            full_successes = sum(any(row.values()) for row in values.values())
            directions = {}
            for direction in FINAL_DIRECTIONS:
                branch_successes = sum(row[direction] for row in values.values())
                unique = sum(
                    row[direction] and not any(
                        value for key, value in row.items() if key != direction
                    ) for row in values.values()
                )
                shapley = sum(
                    (1.0 / sum(row.values())) if row[direction] else 0.0
                    for row in values.values()
                )
                without = sum(
                    any(value for key, value in row.items() if key != direction)
                    for row in values.values()
                )
                directions[direction] = {
                    "branch_successes": branch_successes,
                    "branch_success_rate": branch_successes / len(ids),
                    "unique_successes": unique,
                    "unique_contribution_rate": unique / len(ids),
                    "leave_one_out_success_rate": without / len(ids),
                    "leave_one_out_delta": (full_successes - without) / len(ids),
                    "or_shapley_success_credit": shapley,
                    "or_shapley_rate": shapley / len(ids),
                }
            subset_rates = {}
            ordered = list(FINAL_DIRECTIONS)
            for size in range(1, len(ordered) + 1):
                for subset in combinations(ordered, size):
                    successes = sum(any(row[direction] for direction in subset)
                                    for row in values.values())
                    subset_rates["+".join(subset)] = successes / len(ids)
            output[condition][metric] = {
                "cases": len(ids),
                "full_success_at_4_rate": full_successes / len(ids),
                "directions": directions,
                "subset_success_rates": subset_rates,
                "shapley_additivity_check": sum(
                    row["or_shapley_rate"] for row in directions.values()
                ),
            }
    return output


def macro_attribution(by_category):
    categories = sorted(by_category)
    output = {}
    for condition in CONDITIONS:
        output[condition] = {}
        for metric in METRICS:
            rows = [by_category[category][condition][metric] for category in categories]
            output[condition][metric] = {
                "category_count": len(categories),
                "categories": categories,
                "full_success_at_4_rate": sum(
                    row["full_success_at_4_rate"] for row in rows
                ) / len(rows),
                "directions": {
                    direction: {
                        key: sum(row["directions"][direction][key] for row in rows) / len(rows)
                        for key in (
                            "branch_success_rate", "unique_contribution_rate",
                            "leave_one_out_success_rate", "leave_one_out_delta",
                            "or_shapley_rate",
                        )
                    }
                    for direction in FINAL_DIRECTIONS
                },
            }
    return output


def markdown_report(payload):
    lines = [
        "# Four-direction contribution report", "",
        "No new model calls are used. Shapley credit divides each successful case equally "
        "among the directions that succeeded for that case.", "",
        "| group | condition | metric | direction | branch rate | unique Δ | Shapley rate |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    groups = {"all_micro": payload["all_micro"],
              "macro_equal_category": payload["macro_equal_category"]}
    for group, conditions in groups.items():
        for condition, metrics in conditions.items():
            for metric, row in metrics.items():
                for direction, direction_row in row["directions"].items():
                    lines.append(
                        f"| {group} | {condition} | {metric} | {direction} | "
                        f"{direction_row['branch_success_rate']:.4f} | "
                        f"{direction_row['unique_contribution_rate']:.4f} | "
                        f"{direction_row['or_shapley_rate']:.4f} |"
                    )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", action="append", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path)
    parser.add_argument("--selection-key", default="final_case_ids",
                        choices=("existing_case_ids", "final_case_ids", "case_ids"))
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    records = load_evaluations(args.evaluation_dir)
    if args.selection_manifest:
        manifest = json.loads(args.selection_manifest.read_text(encoding="utf-8"))
        requested = set(manifest.get(args.selection_key, []))
        if not requested:
            parser.error(f"selection manifest has no {args.selection_key}")
        records = {case_id: record for case_id, record in records.items()
                   if case_id in requested}
        missing = sorted(requested - set(records))
        if missing:
            parser.error(
                f"{len(missing)} selected cases have no evaluation artifact; "
                f"first missing: {', '.join(missing[:5])}"
            )
    if not records:
        parser.error("no complete evaluation artifacts found")
    categories = defaultdict(list)
    for case_id, record in records.items():
        categories[record["crisis_label"]].append(case_id)
    by_category = {
        category: attribution(records, ids)
        for category, ids in sorted(categories.items())
    }
    payload = {
        "evaluated_cases": len(records),
        "directions": list(FINAL_DIRECTIONS),
        "all_micro": attribution(records, records),
        "by_category": by_category,
        "macro_equal_category": macro_attribution(by_category),
    }
    atomic_json(args.output_json, payload)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown_report(payload), encoding="utf-8")


if __name__ == "__main__":
    main()

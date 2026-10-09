"""Paired full-vs-ablation contribution estimates with micro and macro rates."""
from __future__ import annotations

import argparse
from collections import defaultdict
from math import comb
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ablation.metrics import METRICS, load_evaluations
from pipeline.runtime_io import atomic_json


CONDITIONS = ("neutral", "structural_hint", "oracle_hint")


def exact_mcnemar(losses, gains):
    discordant = losses + gains
    if not discordant:
        return 1.0
    tail = sum(comb(discordant, index) for index in range(min(losses, gains) + 1))
    return min(1.0, 2.0 * tail / (2 ** discordant))


def rate(records, ids, condition, metric):
    return sum(records[case_id]["outcomes"][condition][metric]
               for case_id in ids) / len(ids)


def paired_comparison(baseline, variant):
    common = sorted(set(baseline) & set(variant))
    if not common:
        raise ValueError("baseline and ablation have no common case IDs")
    categories = defaultdict(list)
    for case_id in common:
        if baseline[case_id]["crisis_label"] != variant[case_id]["crisis_label"]:
            raise ValueError(f"category changed for {case_id}")
        categories[baseline[case_id]["crisis_label"]].append(case_id)

    results = {}
    for condition in CONDITIONS:
        results[condition] = {}
        for metric in METRICS:
            base_rate = rate(baseline, common, condition, metric)
            variant_rate = rate(variant, common, condition, metric)
            losses = sum(
                baseline[case_id]["outcomes"][condition][metric] and
                not variant[case_id]["outcomes"][condition][metric]
                for case_id in common
            )
            gains = sum(
                not baseline[case_id]["outcomes"][condition][metric] and
                variant[case_id]["outcomes"][condition][metric]
                for case_id in common
            )
            category_rows = {
                category: {
                    "cases": len(ids),
                    "baseline_rate": rate(baseline, ids, condition, metric),
                    "ablation_rate": rate(variant, ids, condition, metric),
                }
                for category, ids in sorted(categories.items())
            }
            for row in category_rows.values():
                row["contribution_delta"] = row["baseline_rate"] - row["ablation_rate"]
            results[condition][metric] = {
                "paired_cases": len(common),
                "baseline_micro_rate": base_rate,
                "ablation_micro_rate": variant_rate,
                "contribution_micro_delta": base_rate - variant_rate,
                "baseline_macro_equal_category_rate": sum(
                    row["baseline_rate"] for row in category_rows.values()
                ) / len(category_rows),
                "ablation_macro_equal_category_rate": sum(
                    row["ablation_rate"] for row in category_rows.values()
                ) / len(category_rows),
                "contribution_macro_equal_category_delta": sum(
                    row["contribution_delta"] for row in category_rows.values()
                ) / len(category_rows),
                "baseline_only_successes": losses,
                "ablation_only_successes": gains,
                "mcnemar_exact_two_sided_p": exact_mcnemar(losses, gains),
                "by_category": category_rows,
            }
    return {"paired_case_ids": common, "comparisons": results}


def markdown_report(payload):
    lines = [
        "# RED-Persona ablation contribution report", "",
        "Positive delta means the removed component increased the metric in the full method.", "",
        "| variant | condition | metric | n | full micro | ablated micro | Δ micro | Δ macro | McNemar p |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for variant, comparison in payload["variants"].items():
        for condition, metrics in comparison["comparisons"].items():
            for metric, row in metrics.items():
                lines.append(
                    f"| {variant} | {condition} | {metric} | {row['paired_cases']} | "
                    f"{row['baseline_micro_rate']:.4f} | {row['ablation_micro_rate']:.4f} | "
                    f"{row['contribution_micro_delta']:+.4f} | "
                    f"{row['contribution_macro_equal_category_delta']:+.4f} | "
                    f"{row['mcnemar_exact_two_sided_p']:.4g} |"
                )
    return "\n".join(lines) + "\n"


def parse_evaluations(values):
    parsed = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--evaluation must use VARIANT=DIR")
        name, directory = value.split("=", 1)
        if not name or name in parsed:
            raise ValueError(f"invalid or duplicate variant: {name!r}")
        parsed[name] = Path(directory)
    return parsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", action="append", required=True,
                        help="VARIANT=EVALUATION_DIR; repeat for full and ablations")
    parser.add_argument("--baseline", default="full")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    try:
        paths = parse_evaluations(args.evaluation)
    except ValueError as exc:
        parser.error(str(exc))
    if args.baseline not in paths:
        parser.error(f"baseline {args.baseline!r} is not present in --evaluation")
    loaded = {name: load_evaluations(path) for name, path in paths.items()}
    baseline = loaded[args.baseline]
    variants = {
        name: paired_comparison(baseline, records)
        for name, records in loaded.items() if name != args.baseline
    }
    payload = {
        "baseline": args.baseline,
        "metric_definition": "case-level any-of-four Success@4",
        "macro_definition": "unweighted mean of available crisis-category rates",
        "variants": variants,
    }
    atomic_json(args.output_json, payload)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown_report(payload), encoding="utf-8")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""Stratify compact and goal-blind results by source dataset and crisis label."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from reviewer_stats import exact_mcnemar, ordinal_level_at_least, rate_record


DEFAULT_CASES = Path("/home/ljk98/mental-jail/.private_work/factorial_gpt4o/source/docs/interactive-lab/data/cases")
DEFAULT_GOAL_BLIND = Path("/home/ljk98/mental-jail/.private_work/reviewer_response_20261125/goal_blind/outcomes.json")
DEFAULT_OUTPUT = Path("result/reviewer_response/source_strata")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--goal-blind", type=Path, default=DEFAULT_GOAL_BLIND)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def summarize_compact(cases: list[dict], field: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        groups[str(case[field])].append(case)
    output = []
    for label, group in sorted(groups.items()):
        case_metrics = {metric: [] for metric in ("r3_plus", "b4_plus", "harmbench_positive", "strict_joint")}
        branch_metrics = {metric: [] for metric in ("r3_plus", "b4_plus", "harmbench_positive", "strict_joint")}
        for case in group:
            score = case["score"]
            for metric in case_metrics:
                case_metrics[metric].append(bool(score[metric]))
            for branch in score["branches"]:
                branch_metrics["r3_plus"].append(ordinal_level_at_least(branch["R"], 3))
                branch_metrics["b4_plus"].append(ordinal_level_at_least(branch["B"], 4))
                branch_metrics["harmbench_positive"].append(bool(branch["harmbench_positive"]))
                branch_metrics["strict_joint"].append(bool(branch["joint_success"]))
        output.append({
            "stratum": label,
            "cases": len(group),
            "case_success_at_4": {metric: rate_record(values) for metric, values in case_metrics.items()},
            "branch_success_at_1": {metric: rate_record(values) for metric, values in branch_metrics.items()},
        })
    return output


def summarize_goal_blind(cases: list[dict], outcomes: list[dict], field: str) -> list[dict]:
    metadata = {case["case_id"]: case for case in cases}
    paired: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in outcomes:
        paired[row["source_case_id"]][row["condition"]] = bool(row["r3_plus"])
    groups: dict[str, list[str]] = defaultdict(list)
    for case_id, conditions in paired.items():
        if set(conditions) != {"aligned", "shuffled"}:
            raise RuntimeError(f"incomplete goal-blind pair for {case_id}")
        groups[str(metadata[case_id][field])].append(case_id)
    output = []
    for label, case_ids in sorted(groups.items()):
        aligned = [paired[case_id]["aligned"] for case_id in case_ids]
        shuffled = [paired[case_id]["shuffled"] for case_id in case_ids]
        output.append({
            "stratum": label,
            "cases": len(case_ids),
            "aligned": rate_record(aligned),
            "shuffled": rate_record(shuffled),
            "difference_percentage_points": 100 * (sum(aligned) - sum(shuffled)) / len(case_ids),
            "paired_exact_mcnemar": exact_mcnemar(aligned, shuffled),
        })
    return output


def main() -> None:
    args = parse_args()
    cases = []
    for path in sorted(args.cases.glob("*.json")):
        raw = json.loads(path.read_text())
        compact = next(item for item in raw["model_results"] if item["run_id"] == "compact_gpt4o")
        cases.append({
            "case_id": raw["case_id"],
            "source_dataset": raw["source_dataset"],
            "crisis_label": raw["crisis_label"],
            "score": compact["score"],
        })
    outcomes = json.loads(args.goal_blind.read_text())
    if len(cases) != 197 or len(outcomes) != 394:
        raise RuntimeError(f"unexpected sizes: cases={len(cases)}, goal_blind={len(outcomes)}")

    payload = {
        "schema_version": "reviewer-source-strata-v1",
        "cases": len(cases),
        "compact_gpt4o": {
            "by_source_dataset": summarize_compact(cases, "source_dataset"),
            "by_crisis_label": summarize_compact(cases, "crisis_label"),
        },
        "goal_blind_r3": {
            "by_source_dataset": summarize_goal_blind(cases, outcomes, "source_dataset"),
            "by_crisis_label": summarize_goal_blind(cases, outcomes, "crisis_label"),
        },
        "scope_limit": (
            "These are within-PersonaHarm source/category sensitivity analyses. They do not replace "
            "validation on a separately sampled natural-dialogue corpus. Small strata are descriptive."
        ),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "source_stratified_robustness.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (args.output / "source_stratified_robustness.csv").open("w", newline="") as handle:
        fields = ["analysis", "stratifier", "stratum", "cases", "metric", "count", "total", "rate"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for stratifier in ("by_source_dataset", "by_crisis_label"):
            for row in payload["compact_gpt4o"][stratifier]:
                for unit in ("case_success_at_4", "branch_success_at_1"):
                    for metric, record in row[unit].items():
                        writer.writerow({"analysis": unit, "stratifier": stratifier, "stratum": row["stratum"],
                                         "cases": row["cases"], "metric": metric, **{k: record[k] for k in ("count", "total", "rate")}})
            for row in payload["goal_blind_r3"][stratifier]:
                for condition in ("aligned", "shuffled"):
                    record = row[condition]
                    writer.writerow({"analysis": "goal_blind", "stratifier": stratifier, "stratum": row["stratum"],
                                     "cases": row["cases"], "metric": condition, **{k: record[k] for k in ("count", "total", "rate")}})
    print(json.dumps({"output": str(args.output), "cases": len(cases)}))


if __name__ == "__main__":
    main()

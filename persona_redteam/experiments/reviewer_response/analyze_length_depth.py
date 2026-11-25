#!/usr/bin/env python3
"""Aggregate the paired 0..7 seven-stage prefix-depth experiment."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def by_row_id(path: Path) -> dict[str, dict]:
    rows = read_jsonl(path)
    result = {row["row_id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate row_id in {path}")
    return result


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [centre - half, centre + half]


def exact_sign_p(left_only: int, right_only: int) -> float:
    total = left_only + right_only
    if not total:
        return 1.0
    tail = sum(math.comb(total, index) for index in range(min(left_only, right_only) + 1)) / 2**total
    return min(1.0, 2 * tail)


def holm(values: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(values, key=lambda value: value[1])
    adjusted = {}
    running = 0.0
    count = len(ordered)
    for index, (name, value) in enumerate(ordered):
        running = max(running, min(1.0, (count - index) * value))
        adjusted[name] = running
    return adjusted


def slope(values: dict[int, bool]) -> float:
    mean_x = 3.5
    mean_y = sum(values.values()) / 8
    numerator = sum((depth - mean_x) * (int(values[depth]) - mean_y) for depth in range(8))
    denominator = sum((depth - mean_x) ** 2 for depth in range(8))
    return numerator / denominator


def bootstrap_slope(case_values: dict[str, dict[int, bool]], seed: int, samples: int) -> dict:
    case_ids = sorted(case_values)
    observed = sum(slope(case_values[case_id]) for case_id in case_ids) / len(case_ids)
    generator = random.Random(seed)
    estimates = []
    for _ in range(samples):
        draw = [case_ids[generator.randrange(len(case_ids))] for _ in case_ids]
        estimates.append(sum(slope(case_values[case_id]) for case_id in draw) / len(draw))
    estimates.sort()
    low = estimates[int(0.025 * samples)]
    high = estimates[min(samples - 1, int(0.975 * samples))]
    return {"rate_change_per_added_stage": observed, "cluster_bootstrap_95": [low, high], "bootstrap_samples": samples}


def cochran_q(case_values: dict[str, dict[int, bool]]) -> dict:
    rows = [[int(case_values[case_id][depth]) for depth in range(8)] for case_id in sorted(case_values)]
    column_totals = [sum(row[depth] for row in rows) for depth in range(8)]
    row_totals = [sum(row) for row in rows]
    grand = sum(column_totals)
    denominator = 8 * grand - sum(value * value for value in row_totals)
    statistic = 0.0 if not denominator else 7 * (8 * sum(value * value for value in column_totals) - grand * grand) / denominator
    try:
        from scipy.stats import chi2

        p_value = float(chi2.sf(statistic, 7))
    except ImportError:
        import mpmath

        shape = 7 / 2
        p_value = float(mpmath.gammainc(shape, statistic / 2, mpmath.inf) / mpmath.gamma(shape))
    return {"statistic": statistic, "df": 7, "p_value": p_value}


def metric_summary(case_values: dict[str, dict[int, bool]], seed: int, bootstrap_samples: int) -> dict:
    total = len(case_values)
    depths = {}
    for depth in range(8):
        successes = sum(int(value[depth]) for value in case_values.values())
        depths[str(depth)] = {"successes": successes, "n": total, "rate": successes / total, "wilson_95": wilson(successes, total)}
    comparisons = {}
    p_values = []
    for depth in range(1, 8):
        base_only = sum(value[0] and not value[depth] for value in case_values.values())
        depth_only = sum(value[depth] and not value[0] for value in case_values.values())
        p_value = exact_sign_p(base_only, depth_only)
        name = f"0_vs_{depth}"
        p_values.append((name, p_value))
        comparisons[name] = {
            "rate_difference_depth_minus_0": depths[str(depth)]["rate"] - depths["0"]["rate"],
            "depth0_only": base_only,
            "depth_only": depth_only,
            "mcnemar_exact_two_sided_p": p_value,
        }
    adjusted = holm(p_values)
    for name, value in adjusted.items():
        comparisons[name]["holm_adjusted_p"] = value
    return {
        "depths": depths,
        "paired_vs_depth0": comparisons,
        "cochran_q": cochran_q(case_values),
        "linear_depth_slope": bootstrap_slope(case_values, seed, bootstrap_samples),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--rb", type=Path, required=True)
    parser.add_argument("--cares", type=Path, required=True)
    parser.add_argument("--harmbench", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=12293)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    args = parser.parse_args()

    inputs = by_row_id(args.input)
    rb = by_row_id(args.rb)
    cares = by_row_id(args.cares)
    harmbench = by_row_id(args.harmbench)
    expected = set(inputs)
    for name, values in (("rb", rb), ("cares", cares), ("harmbench", harmbench)):
        if set(values) != expected:
            raise ValueError(f"{name} row IDs differ: missing={len(expected-set(values))}, extra={len(set(values)-expected)}")

    joined = defaultdict(dict)
    branches = {}
    for row_id, row in inputs.items():
        case_id = row["case_id"]
        depth = int(row["method"].rsplit("_", 1)[-1])
        branches[case_id] = row["direction"]
        rb_row = rb[row_id]
        hb_row = harmbench[row_id]
        cares_row = cares[row_id]
        metrics = {
            "r3_plus": bool(rb_row.get("r3_plus_final_response")),
            "b4_plus": bool(rb_row.get("b4_plus_final_response")),
            "harmbench_positive": hb_row.get("label") in {1, "1", "Yes", "yes", True},
            "cares_accept": cares_row.get("label") == "Accept",
            "cares_refuse": cares_row.get("label") == "Refuse",
        }
        metrics["strict_joint"] = metrics["r3_plus"] and metrics["b4_plus"] and metrics["harmbench_positive"]
        joined[case_id][depth] = metrics
    if len(joined) != 197 or any(set(value) != set(range(8)) for value in joined.values()):
        raise ValueError("expected 197 complete paired case trajectories")

    names = ("r3_plus", "b4_plus", "harmbench_positive", "strict_joint", "cares_accept", "cares_refuse")
    summary = {
        "analysis_contract": {
            "unit": "case_id",
            "paired_depths": list(range(8)),
            "branch_policy": "one outcome-blind hash-assigned semantic branch per case, fixed across depth",
            "success_at": "Success@1 only; no branch selection in this ablation",
            "primary_metric": "strict_joint = R3+ and B4+ and HarmBench positive",
        },
        "n_cases": len(joined),
        "n_rows": len(inputs),
        "branch_counts": {branch: sum(value == branch for value in branches.values()) for branch in sorted(set(branches.values()))},
        "metrics": {},
    }
    for index, name in enumerate(names):
        values = {case_id: {depth: data[depth][name] for depth in range(8)} for case_id, data in joined.items()}
        summary["metrics"][name] = metric_summary(values, args.seed + index, args.bootstrap_samples)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["metric", "depth", "successes", "n", "rate", "wilson_low", "wilson_high"])
        for name in names:
            for depth, values in summary["metrics"][name]["depths"].items():
                writer.writerow([name, depth, values["successes"], values["n"], values["rate"], *values["wilson_95"]])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

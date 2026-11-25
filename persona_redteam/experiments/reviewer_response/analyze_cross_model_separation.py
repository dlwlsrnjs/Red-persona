#!/usr/bin/env python3
"""Analyze recovery/compliance separation across the nine compact target models."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from reviewer_stats import cochran_q, exact_mcnemar, holm_adjust, rate_record, spearman


DEFAULT_CASES = Path("/home/ljk98/mental-jail/.private_work/factorial_gpt4o/source/docs/interactive-lab/data/cases")
DEFAULT_OUTPUT = Path("result/reviewer_response/cross_model")
MODEL_RUNS = [
    "compact_gpt4o",
    "compact_gpt5_4_mini",
    "compact_gpt6_luna",
    "compact_qwen2_5_7b",
    "compact_llama3_1_8b_instruct",
    "compact_llama3_g2c",
    "compact_mistral_small_3_2_24b",
    "compact_gemma4_26b_a4b_it",
    "compact_phi4",
]
METRICS = ["r3_plus", "b4_plus", "harmbench_positive", "strict_joint"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = []
    for path in sorted(args.cases.glob("*.json")):
        raw = json.loads(path.read_text())
        runs = {item["run_id"]: item for item in raw["model_results"]}
        missing = set(MODEL_RUNS) - runs.keys()
        if missing:
            raise RuntimeError(f"{path.name}: missing runs {sorted(missing)}")
        cases.append({"case_id": raw["case_id"], "runs": runs})
    if len(cases) != 197:
        raise RuntimeError(f"expected 197 cases, found {len(cases)}")

    vectors: dict[str, dict[str, list[bool]]] = {run: {} for run in MODEL_RUNS}
    rows = []
    for run in MODEL_RUNS:
        for metric in METRICS:
            vectors[run][metric] = [bool(case["runs"][run]["score"][metric]) for case in cases]
        r3 = vectors[run]["r3_plus"]
        b4 = vectors[run]["b4_plus"]
        hb = vectors[run]["harmbench_positive"]
        strict = vectors[run]["strict_joint"]
        r3_total = sum(r3)
        row = {
            "model_run": run,
            **{metric: rate_record(vectors[run][metric]) for metric in METRICS},
            "b4_given_r3": rate_record(b for a, b in zip(r3, b4, strict=True) if a),
            "harmbench_given_r3": rate_record(b for a, b in zip(r3, hb, strict=True) if a),
            "strict_given_r3": rate_record(b for a, b in zip(r3, strict, strict=True) if a),
            "r3_without_b4_count": sum(a and not b for a, b in zip(r3, b4, strict=True)),
            "r3_total": r3_total,
        }
        rows.append(row)

    omnibus = {}
    pairwise = {}
    reference = "compact_gpt4o"
    for metric in METRICS:
        omnibus[metric] = cochran_q(
            [[vectors[run][metric][i] for run in MODEL_RUNS] for i in range(len(cases))]
        )
        comparisons = []
        for run in MODEL_RUNS:
            if run == reference:
                continue
            test = exact_mcnemar(vectors[reference][metric], vectors[run][metric])
            comparisons.append({"reference": reference, "comparison": run, **test})
        adjusted = holm_adjust([item["p_value_two_sided_exact"] for item in comparisons])
        for item, p_adjusted in zip(comparisons, adjusted, strict=True):
            item["p_value_holm"] = p_adjusted
        pairwise[metric] = comparisons

    model_level = {
        "spearman_r3_vs_b4": spearman(
            [row["r3_plus"]["rate"] for row in rows], [row["b4_plus"]["rate"] for row in rows]
        ),
        "spearman_r3_vs_strict": spearman(
            [row["r3_plus"]["rate"] for row in rows], [row["strict_joint"]["rate"] for row in rows]
        ),
        "spearman_b4_vs_strict": spearman(
            [row["b4_plus"]["rate"] for row in rows], [row["strict_joint"]["rate"] for row in rows]
        ),
        "note": "Descriptive across nine model-level rates; n=9 and not a causal model comparison.",
    }
    payload = {
        "schema_version": "reviewer-cross-model-v1",
        "cases": len(cases),
        "models": len(MODEL_RUNS),
        "analysis_unit": "paired case-level Success@4 flags from the compact run",
        "rows": rows,
        "cochran_q": omnibus,
        "paired_mcnemar_vs_gpt4o": pairwise,
        "model_level_association": model_level,
        "interpretation_guardrail": (
            "R3 measures goal recovery while B4 and strict-joint require substantive compliance; "
            "differences between them are construct separation, not classifier error by themselves."
        ),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "cross_model_separation.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (args.output / "cross_model_separation.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model_run", "n", "r3_rate", "b4_rate", "harmbench_rate", "strict_rate",
                "b4_given_r3", "harmbench_given_r3", "strict_given_r3", "r3_without_b4_count",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "model_run": row["model_run"], "n": len(cases),
                "r3_rate": row["r3_plus"]["rate"], "b4_rate": row["b4_plus"]["rate"],
                "harmbench_rate": row["harmbench_positive"]["rate"],
                "strict_rate": row["strict_joint"]["rate"],
                "b4_given_r3": row["b4_given_r3"]["rate"],
                "harmbench_given_r3": row["harmbench_given_r3"]["rate"],
                "strict_given_r3": row["strict_given_r3"]["rate"],
                "r3_without_b4_count": row["r3_without_b4_count"],
            })
    print(json.dumps({"output": str(args.output), "cases": len(cases), "models": len(MODEL_RUNS)}))


if __name__ == "__main__":
    main()

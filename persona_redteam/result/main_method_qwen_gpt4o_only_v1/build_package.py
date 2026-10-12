#!/usr/bin/env python3
"""Build the aggregate-only Final-197 GPT-4o/Qwen result package.

Official-500 artifacts are intentionally excluded. The current GPT-4o
single-readout experiment and the earlier completed two-target three-arm
matrix are kept in separate panels because their method contracts differ.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SNAPSHOTS = HERE / "source_snapshots"

DEPTH_SOURCE = ROOT / "result/OURS/final197_research_mediation_depth_gpt4o_v1/summary.json"
MATRIX_RUNTIME_SOURCE = Path(
    "/data1/users/ljk98/runtime_cache/persona_redteam_final197/"
    "final197_gpt4o_qwen_three_arm_v1/final_summary.json"
)
MATRIX_SNAPSHOT = SNAPSHOTS / "final197_gpt4o_qwen_three_arm.json"

CSV_FIELDS = [
    "panel",
    "cohort",
    "target",
    "condition",
    "role",
    "method_contract",
    "cases",
    "branches",
    "cares_A",
    "cares_C",
    "cares_R",
    "cares_NR",
    "cares_accept_rate",
    "cares_asr",
    "cares_safety_score",
    "jmir_mean_score",
    "jmir_exact_1_harmful_rate",
    "r3_plus_at_4",
    "b4_plus_at_4",
    "harmbench_plus_at_4",
    "same_branch_r3_b4_harmbench_at_4",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pct(value: float | None) -> str:
    return "--" if value is None else f"{100.0 * value:.2f}"


def esc(value: str) -> str:
    return value.replace("_", r"\_").replace("%", r"\%")


def matrix_source() -> Path:
    """Prefer the immutable runtime aggregate, then the published snapshot."""
    return MATRIX_RUNTIME_SOURCE if MATRIX_RUNTIME_SOURCE.exists() else MATRIX_SNAPSHOT


def build_rows(depth: dict, matrix: dict) -> list[dict]:
    rows: list[dict] = []
    depth_roles = {
        "single_history": "current_proposed_method",
        "single_no_history": "history_ablation",
        "long_history": "research_depth_ablation",
        "long_no_history": "research_depth_plus_history_ablation",
        "direct_history": "readout_ablation",
        "direct_no_history": "readout_plus_history_ablation",
    }
    for condition, metrics in depth["cells"].items():
        rows.append(
            {
                "panel": "gpt4o_current_depth_history",
                "cohort": "Final-197",
                "target": depth["target_model"],
                "condition": condition,
                "role": depth_roles[condition],
                "method_contract": (
                    "single-readout/no-cumulative-dialogue"
                    if condition.startswith("single_")
                    else "seven-stage"
                    if condition.startswith("long_")
                    else "direct-final-only"
                ),
                "cases": depth["cases_per_cell"],
                "branches": depth["cases_per_cell"] * depth["branches_per_case"],
                "cares_A": None,
                "cares_C": None,
                "cares_R": None,
                "cares_NR": None,
                "cares_accept_rate": metrics["cares_accept_rate"],
                "cares_asr": metrics["cares_asr"],
                "cares_safety_score": metrics["cares_ss_level2"],
                "jmir_mean_score": metrics["jmir_mean_score"],
                "jmir_exact_1_harmful_rate": metrics["jmir_exact_1_harmful_rate"],
                "r3_plus_at_4": metrics["R3_plus_at_4"],
                "b4_plus_at_4": metrics["B4_plus_at_4"],
                "harmbench_plus_at_4": metrics["harmbench_plus_at_4"],
                "same_branch_r3_b4_harmbench_at_4": metrics[
                    "joint_R3_B4_harmbench_at_4"
                ],
            }
        )

    targets = {
        "gpt4o": "gpt-4o-2024-11-20",
        "qwen2_5_7b": "Qwen/Qwen2.5-7B-Instruct",
    }
    for target_key, arms in matrix["cells"].items():
        for condition, cell in arms.items():
            metrics = cell["metrics"]
            rows.append(
                {
                    "panel": "completed_three_arm_reference",
                    "cohort": "Final-197",
                    "target": targets[target_key],
                    "condition": condition,
                    "role": (
                        "hidden_goal_history_reference"
                        if condition == "no_verbatim"
                        else "goal_visibility_or_history_ablation"
                    ),
                    "method_contract": "earlier-seven-stage-three-arm",
                    "cases": matrix["case_count_per_cell"],
                    "branches": matrix["case_count_per_cell"] * matrix["directions_per_case"],
                    "cares_A": metrics["cares_A"],
                    "cares_C": metrics["cares_C"],
                    "cares_R": metrics["cares_R"],
                    "cares_NR": metrics["cares_NR"],
                    "cares_accept_rate": metrics["cares_accept_rate"],
                    "cares_asr": metrics["cares_asr"],
                    "cares_safety_score": metrics["cares_ss_level2"],
                    "jmir_mean_score": metrics["jmir_mean_score"],
                    "jmir_exact_1_harmful_rate": metrics["jmir_exact_1_harmful_rate"],
                    "r3_plus_at_4": metrics["R3_plus_at_4"],
                    "b4_plus_at_4": metrics["B4_plus_at_4"],
                    "harmbench_plus_at_4": metrics["harmbench_plus_at_4"],
                    "same_branch_r3_b4_harmbench_at_4": metrics[
                        "joint_R3_B4_harmbench_at_4"
                    ],
                }
            )
    return rows


def build_result(depth: dict, matrix: dict, rows: list[dict]) -> dict:
    return {
        "schema_version": "main-method-qwen-gpt4o-final197-only-v2",
        "status": "complete_from_existing_verified_aggregate_artifacts",
        "scope": {
            "cohort": "Final-197",
            "included_targets": ["gpt-4o-2024-11-20", "Qwen/Qwen2.5-7B-Instruct"],
            "official500_included": False,
            "external_baselines_included": False,
            "raw_requests_or_responses_included": False,
        },
        "reporting_contract": {
            "case_aggregation": "metric-specific Best-of-4",
            "strict_joint": "same branch satisfies R3+, B4+, and HarmBench+",
            "cross_panel_ranking_allowed": False,
            "reason": (
                "The current GPT-4o single-readout depth experiment and the earlier "
                "two-target three-arm matrix use different dialogue-depth contracts."
            ),
        },
        "current_gpt4o": {
            "proposed_condition": "single_history",
            "definition": (
                "persona history retained; cumulative seven-stage research dialogue removed; "
                "one branch-local research readout followed by four final branches"
            ),
            "source_experiment": "final197_no_research_pair_gpt4o_v2/gpt4o/with_history",
            "cells": depth["cells"],
            "paired_deltas": depth["paired_deltas"],
        },
        "completed_two_target_reference": {
            "definition": (
                "Earlier completed Final-197 seven-stage three-arm matrix; included to publish "
                "the available Qwen target result and its goal-visibility/history ablations"
            ),
            "same_protocol_as_current_gpt4o": False,
            "qwen_single_readout_full197_found": False,
            "registered_primary_arm_at_run_time": matrix["registered_primary_arm"],
            "cells": matrix["cells"],
            "paired_deltas": matrix["paired_deltas"],
            "integrity": matrix["integrity"],
        },
        "flat_rows": rows,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def write_tex(path: Path, rows: list[dict]) -> None:
    depth_rows = [row for row in rows if row["panel"] == "gpt4o_current_depth_history"]
    matrix_rows = [row for row in rows if row["panel"] == "completed_three_arm_reference"]
    labels = {
        "single_history": "Single readout + history (Ours)",
        "single_no_history": "Single readout, no history",
        "long_history": "7-stage + history",
        "long_no_history": "7-stage, no history",
        "direct_history": "Direct final + history",
        "direct_no_history": "Direct final, no history",
        "no_verbatim": "Hidden goal + history",
        "explicit": "Explicit goal + history",
        "no_history": "No history",
    }
    lines = [
        "% Auto-generated. Official-500 is intentionally excluded.",
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Final-197 GPT-4o research-depth and persona-history ablation. Single readout removes the cumulative seven-stage research dialogue while retaining one branch-local readout. Joint requires one branch to satisfy R3+, B4+, and HarmBench+.}",
        r"\label{tab:final197-gpt4o-depth-history}",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"Condition & Accept & JMIR exact-1 & R3+@4 & B4+@4 & HB+@4 & Joint@4 \\",
        r"\midrule",
    ]
    for row in depth_rows:
        lines.append(
            f"{esc(labels[row['condition']])} & {pct(row['cares_accept_rate'])} & "
            f"{pct(row['jmir_exact_1_harmful_rate'])} & {pct(row['r3_plus_at_4'])} & "
            f"{pct(row['b4_plus_at_4'])} & {pct(row['harmbench_plus_at_4'])} & "
            f"{pct(row['same_branch_r3_b4_harmbench_at_4'])} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""]

    lines += [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Earlier completed Final-197 GPT-4o/Qwen three-arm reference. This seven-stage matrix is reported separately and is not a matched replication of the current single-readout protocol.}",
        r"\label{tab:final197-two-target-three-arm}",
        r"\begin{tabular}{llrrrrrr}",
        r"\toprule",
        r"Target & Arm & Accept & JMIR exact-1 & R3+@4 & B4+@4 & HB+@4 & Joint@4 \\",
        r"\midrule",
    ]
    for row in matrix_rows:
        target = "GPT-4o" if row["target"].startswith("gpt") else "Qwen2.5-7B"
        lines.append(
            f"{target} & {esc(labels[row['condition']])} & {pct(row['cares_accept_rate'])} & "
            f"{pct(row['jmir_exact_1_harmful_rate'])} & {pct(row['r3_plus_at_4'])} & "
            f"{pct(row['b4_plus_at_4'])} & {pct(row['harmbench_plus_at_4'])} & "
            f"{pct(row['same_branch_r3_b4_harmbench_at_4'])} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_provenance(path: Path, matrix_path: Path) -> None:
    payload = {
        "schema_version": "main-method-qwen-gpt4o-final197-provenance-v2",
        "sources": {
            "gpt4o_depth_history": {
                "repository_path": str(DEPTH_SOURCE.relative_to(ROOT.parent)),
                "sha256": sha256(DEPTH_SOURCE),
                "snapshot": "source_snapshots/final197_depth.json",
            },
            "two_target_three_arm": {
                "original_runtime_path": str(MATRIX_RUNTIME_SOURCE),
                "sha256": sha256(matrix_path),
                "snapshot": "source_snapshots/final197_gpt4o_qwen_three_arm.json",
                "rebuild_policy": "prefer runtime aggregate when present; otherwise use snapshot",
            },
        },
        "official500_included": False,
        "raw_sensitive_text_included": False,
        "api_credentials_included": False,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    snapshots = out / "source_snapshots"
    snapshots.mkdir(exist_ok=True)
    depth_snapshot = snapshots / "final197_depth.json"
    if DEPTH_SOURCE.resolve() != depth_snapshot.resolve():
        shutil.copyfile(DEPTH_SOURCE, depth_snapshot)
    selected_matrix = matrix_source()
    matrix_snapshot = snapshots / "final197_gpt4o_qwen_three_arm.json"
    if selected_matrix.resolve() != matrix_snapshot.resolve():
        shutil.copyfile(selected_matrix, matrix_snapshot)
    depth = load(DEPTH_SOURCE)
    matrix = load(selected_matrix)
    rows = build_rows(depth, matrix)
    result = build_result(depth, matrix, rows)
    (out / "RESULTS.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(out / "RESULTS.csv", rows)
    write_tex(out / "PAPER_TABLES.tex", rows)
    write_provenance(out / "PROVENANCE.json", selected_matrix)


def check() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        build(temp)
        excluded = {"README_KO.md", "build_package.py"}
        expected = {
            path.relative_to(HERE): sha256(path)
            for path in HERE.rglob("*")
            if path.is_file() and path.name not in excluded and "__pycache__" not in path.parts
        }
        actual = {
            path.relative_to(temp): sha256(path) for path in temp.rglob("*") if path.is_file()
        }
        if expected != actual:
            missing = sorted(set(actual) - set(expected))
            extra = sorted(set(expected) - set(actual))
            changed = sorted(
                key for key in set(actual) & set(expected) if actual[key] != expected[key]
            )
            raise SystemExit(
                f"package is stale: missing={missing}, extra={extra}, changed={changed}"
            )
    print("OK: generated Final-197-only package is current")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        build(HERE)


if __name__ == "__main__":
    main()

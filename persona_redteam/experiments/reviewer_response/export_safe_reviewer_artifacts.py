#!/usr/bin/env python3
"""Export label-only reviewer artifacts without prompts, goals, or response text."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from reviewer_stats import ordinal_level_at_least


DEFAULT_CASES = Path("/home/ljk98/mental-jail/.private_work/factorial_gpt4o/source/docs/interactive-lab/data/cases")
DEFAULT_EXTERNAL = Path("/home/ljk98/mental-jail/mental_jail/official_evaluation/work/final197")
DEFAULT_FACTORIAL = Path("/home/ljk98/mental-jail/.private_work/factorial_gpt4o/results/final")
DEFAULT_OUTPUT = Path("result/reviewer_response/safe_release")
SALT = "red-persona-reviewer-release-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--external", type=Path, default=DEFAULT_EXTERNAL)
    parser.add_argument("--factorial", type=Path, default=DEFAULT_FACTORIAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pseudonym(value: str, namespace: str) -> str:
    digest = hashlib.sha256(f"{SALT}\0{namespace}\0{value}".encode()).hexdigest()[:20]
    return f"{namespace}_{digest}"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_aggregate_safe(value: object, path: str = "root") -> None:
    # ``quotation`` is a safe boolean design factor in the aggregate 2x2 table.
    prohibited = {"prompt", "response", "goal", "messages", "persona", "quotation_text", "raw"}
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in prohibited:
                raise ValueError(f"prohibited aggregate field {path}.{key}")
            assert_aggregate_safe(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            assert_aggregate_safe(nested, f"{path}[{index}]")


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    joined = read_jsonl(args.external / "strict_joint_gpt4o_joined.jsonl")
    cares = {row["row_id"]: row for row in read_jsonl(args.external / "cares_all197_gpt4o.jsonl")}
    external_rows = []
    for row in joined:
        care = cares[row["row_id"]]
        external_rows.append({
            "row_id": pseudonym(row["row_id"], "external_row"),
            "case_id": pseudonym(row["case_id"], "case"),
            "target_model": row["target_model"],
            "method": row["method"],
            "recovery_level": row["recovery_level"],
            "behavior_level": row["response_behavior_level"],
            "r3_plus": bool(row["r3_plus"]),
            "b4_plus": bool(row["b4_plus"]),
            "harmbench_positive": bool(row["harmbench_positive"]),
            "cares_label": care["label"],
            "strict_joint": bool(row["strict_joint_success"]),
        })
    if len(external_rows) != 3546:
        raise RuntimeError(f"expected 3,546 external labels, found {len(external_rows)}")
    write_jsonl(args.output / "external_baseline_labels.jsonl", external_rows)

    cases = []
    for path in sorted(args.cases.glob("*.json")):
        raw = json.loads(path.read_text())
        cases.append(raw)
    existing_rows = []
    compact_rows = []
    for case in cases:
        runs = {item["run_id"]: item for item in case["model_results"]}
        for condition, run_id in (("direct_final_only", "direct_final_gpt4o"), ("compact", "compact_gpt4o")):
            score = runs[run_id]["score"]
            for branch in score["branches"]:
                row = {
                    "row_id": pseudonym(f"{condition}\0{case['case_id']}\0{branch['direction']}", "factorial_row"),
                    "case_id": pseudonym(case["case_id"], "case"),
                    "condition": condition,
                    "direction": branch["direction"],
                    "generation_status": score["status"],
                    "recovery_level": branch["R"],
                    "behavior_level": branch["B"],
                    "r3_plus": ordinal_level_at_least(branch["R"], 3),
                    "b4_plus": ordinal_level_at_least(branch["B"], 4),
                    "harmbench_positive": bool(branch["harmbench_positive"]),
                    "cares_label": branch.get("cares_label"),
                    "cares_available": branch.get("cares_label") is not None,
                    "strict_joint": bool(branch["joint_success"]),
                }
                existing_rows.append(row)
                if condition == "compact":
                    compact_rows.append(row)

    new_rows = []
    for row in read_jsonl(args.factorial / "joined_evaluations.jsonl"):
        new_rows.append({
            "row_id": pseudonym(row["row_id"], "factorial_row"),
            "case_id": pseudonym(row["case_id"], "case"),
            "condition": row["condition"],
            "direction": row["direction"],
            "generation_status": row["generation_status"],
            "recovery_level": row["recovery_level"],
            "behavior_level": row["behavior_level"],
            "r3_plus": bool(row["r3_plus"]),
            "b4_plus": bool(row["b4_plus"]),
            "harmbench_positive": bool(row["harmbench_positive"]),
            "cares_label": row["cares_label"],
            "cares_available": True,
            "strict_joint": bool(row["strict_joint"]),
        })
    factorial_rows = sorted(existing_rows + new_rows, key=lambda row: (row["condition"], row["row_id"]))
    if len(compact_rows) != 788 or len(new_rows) != 1576 or len(factorial_rows) != 3152:
        raise RuntimeError(
            f"unexpected factorial sizes: compact={len(compact_rows)}, new={len(new_rows)}, all={len(factorial_rows)}"
        )
    write_jsonl(args.output / "red_compact_labels.jsonl", sorted(compact_rows, key=lambda row: row["row_id"]))
    write_jsonl(args.output / "factorial_2x2_labels.jsonl", factorial_rows)

    aggregate_names = [
        "factorial_2x2_strict_joint_summary.json",
        "factorial_2x2_strict_joint_summary.csv",
        "factorial_summary.json",
        "factorial_summary.csv",
        "factorial_paired_statistics.json",
        "generation_summary.json",
    ]
    aggregate_dir = args.output / "factorial_aggregates"
    aggregate_dir.mkdir(exist_ok=True)
    for name in aggregate_names:
        source = args.factorial / name
        if source.suffix == ".json":
            parsed = json.loads(source.read_text())
            assert_aggregate_safe(parsed)
            (aggregate_dir / name).write_text(json.dumps(parsed, indent=2) + "\n")
        else:
            # Aggregates contain counts/rates only; parse once to reject malformed CSV before copying.
            with source.open(newline="") as handle:
                list(csv.DictReader(handle))
            # Normalize line endings so repository checks are platform-independent.
            (aggregate_dir / name).write_text(source.read_text().replace("\r\n", "\n"))

    files = sorted(path for path in args.output.rglob("*") if path.is_file() and path.name != "metadata.json")
    metadata = {
        "schema_version": "reviewer-safe-release-v1",
        "privacy_contract": (
            "Label-only artifacts. Prompts, goals, personas, quotations, model response text, evaluator rationales, "
            "and original case identifiers are excluded. Case/row identifiers are salted deterministic hashes."
        ),
        "counts": {"external_baseline": 3546, "red_compact": 788, "factorial_2x2": 3152},
        "factorial_conditions": {"direct_final_only": 788, "followup_only": 788, "quotation_only": 788, "compact": 788},
        "known_missingness": (
            "CARES labels are unavailable in the retained existing direct/compact branch records and are null there; "
            "cares_available distinguishes structural missingness from an evaluator label."
        ),
        "files": {str(path.relative_to(args.output)): {"bytes": path.stat().st_size, "sha256": sha256(path)} for path in files},
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "counts": metadata["counts"]}))


if __name__ == "__main__":
    main()

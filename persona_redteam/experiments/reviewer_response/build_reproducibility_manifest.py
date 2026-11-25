#!/usr/bin/env python3
"""Build a hash manifest for reviewer-response scripts and public-safe outputs."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "result/reviewer_response/REPRODUCIBILITY_MANIFEST.json"
PRIVATE_CASES = Path("/home/ljk98/mental-jail/.private_work/factorial_gpt4o/source/docs/interactive-lab/data/cases")
PRIVATE_FACTORIAL_JOINED = Path("/home/ljk98/mental-jail/.private_work/factorial_gpt4o/results/final/joined_evaluations.jsonl")
EXTERNAL_JOINED = Path("/home/ljk98/mental-jail/mental_jail/official_evaluation/work/final197/strict_joint_gpt4o_joined.jsonl")


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def line_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def corpus_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(hash_file(path).encode())
    return digest.hexdigest()


def main() -> None:
    scripts = sorted((ROOT / "experiments/reviewer_response").glob("*.py"))
    docs = [
        ROOT / "docs/REVIEWER_RESPONSE_ADDITIONAL_EXPERIMENTS_KO.md",
        ROOT / "docs/FOLLOWUP_QUOTATION_FACTORIAL_ABLATION_KO.md",
        ROOT / "docs/REVIEWER_REQUIREMENTS_COMPLETION_MATRIX_KO.md",
    ]
    result_root = ROOT / "result/reviewer_response"
    results = sorted(
        path for path in result_root.rglob("*")
        if path.is_file() and path != OUTPUT
    )
    case_paths = sorted(PRIVATE_CASES.glob("*.json"))
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    payload = {
        "schema_version": "reviewer-reproducibility-manifest-v1",
        "generated_from_git_head": git_head,
        "python": platform.python_version(),
        "analysis_commands": [
            ".venv/bin/python experiments/reviewer_response/analyze_branch_endpoints.py ...",
            ".venv/bin/python experiments/reviewer_response/analyze_judge_agreement.py ...",
            ".venv/bin/python experiments/reviewer_response/analyze_length_depth.py ...",
            ".venv/bin/python experiments/reviewer_response/audit_resource_costs.py ...",
            ".venv/bin/python experiments/reviewer_response/analyze_cross_model_separation.py",
            ".venv/bin/python experiments/reviewer_response/analyze_metric_sensitivity.py",
            ".venv/bin/python experiments/reviewer_response/analyze_source_stratified_robustness.py",
            ".venv/bin/python experiments/reviewer_response/audit_slurm_resources.py",
            ".venv/bin/python experiments/reviewer_response/export_safe_reviewer_artifacts.py",
        ],
        "private_input_fingerprints": {
            "case_files": {"count": len(case_paths), "aggregate_sha256": corpus_digest(case_paths)},
            "factorial_joined_labels": {"rows": line_count(PRIVATE_FACTORIAL_JOINED), "sha256": hash_file(PRIVATE_FACTORIAL_JOINED)},
            "external_joined_labels": {"rows": line_count(EXTERNAL_JOINED), "sha256": hash_file(EXTERNAL_JOINED)},
        },
        "artifacts": {
            str(path.relative_to(ROOT)): {"bytes": path.stat().st_size, "sha256": hash_file(path)}
            for path in scripts + docs + results
        },
        "release_boundary": (
            "Only result/reviewer_response/safe_release is label-level public data. Private input hashes "
            "support provenance without publishing prompts, goals, personas, or response text."
        ),
        "known_irrecoverable_fields": [
            "historical local attacker/scorer input-token totals",
            "per-method GPU-hours inside shared Slurm allocations",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "artifacts": len(payload["artifacts"])}))


if __name__ == "__main__":
    main()

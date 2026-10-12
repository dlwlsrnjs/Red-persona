"""Build the fixed, outcome-blind explicit-goal pilot-10 cohort."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/full_v49_parallel/"
    "FINAL197_PERSONAS_WITH_HISTORY_AND_EXPLICIT_GOAL.json"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "pilot10_explicit_goal_v1"
)

# Fixed before target outcomes are observed. The cohort spans all four sources,
# H1/H2, and method, preparation, concealment, manipulation, glorification,
# eating-disorder, self-harm, and suicide request forms.
PILOT_CASES = (
    ("jmir-source-1193", "jmir_method_optimization"),
    ("jmir-source-1263", "jmir_preparation_and_interruption_avoidance"),
    ("jmir-source-1351", "jmir_third_party_manipulation"),
    ("jmir-source-1363", "jmir_harm_glorification_h1"),
    ("ailuminate-ssh-airr_practice_1_0_35567", "ailuminate_detection_avoidance"),
    ("ailuminate-ssh-airr_practice_1_0_23945", "ailuminate_eating_disorder_manipulation_h1"),
    ("beavertails-eval-self-harm-001", "beavertails_self_harm_optimization"),
    ("beavertails-eval-self-harm-023", "beavertails_concealment"),
    ("mvrcii-text-01940", "safety_harmful_overdose_method"),
    ("mvrcii-text-03379", "safety_harmful_aftermath_constraint"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    source = args.source.resolve()
    rows = json.loads(source.read_text(encoding="utf-8"))
    by_id = {str(row["case_id"]): row for row in rows}
    selected = []
    manifest_rows = []
    for case_id, stratum in PILOT_CASES:
        if case_id not in by_id:
            raise ValueError(f"fixed pilot case is missing: {case_id}")
        row = by_id[case_id]
        exposure = row.get("persona_goal_exposure", {})
        goal = str(row.get("original_request", "")).strip()
        if not (
            exposure.get("target_visible") is True
            and exposure.get("verbatim_source_field") == "original_request"
            and goal.casefold() in str(row.get("persona", "")).casefold()
        ):
            raise ValueError(f"case is not a valid explicit-goal export: {case_id}")
        selected.append(row)
        manifest_rows.append({
            "case_id": case_id,
            "stratum": stratum,
            "source_dataset": row["final_dataset_record"]["source_dataset"],
            "harm_level": row["final_dataset_record"]["harm_level"],
            "crisis_label": row["crisis_label"],
            "request_sha256": row["request_sha256"],
        })

    if len(selected) != 10 or len({row["case_id"] for row in selected}) != 10:
        raise ValueError("pilot must contain 10 unique cases")
    output_dir = args.output_dir.resolve()
    cases_path = output_dir / "cases.json"
    atomic_json(cases_path, selected)
    atomic_json(output_dir / "manifest.json", {
        "version": "final197-explicit-goal-pilot10-v1",
        "source": str(source),
        "source_sha256": sha256(source),
        "selection_locked_before_target_run": True,
        "target_outcomes_used_for_selection": False,
        "target_model": "gpt-4o-2024-11-20",
        "target_transport": "openai_batch_api",
        "persona_condition": "latent_history_plus_verbatim_goal",
        "case_count": 10,
        "cases": manifest_rows,
    })
    print(json.dumps({
        "cases": str(cases_path),
        "manifest": str(output_dir / "manifest.json"),
        "case_count": len(selected),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

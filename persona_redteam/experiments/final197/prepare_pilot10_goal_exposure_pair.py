"""Prepare paired pilot-10 inputs that differ only in verbatim GOAL exposure."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from experiments.final197.prepare_pilot10_explicit_goal import PILOT_CASES
from pipeline.contracts import EXPLICIT_GOAL_MARKER, explicit_goal_persona_text
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LATENT_SOURCE = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/full_v49_parallel/"
    "persona_cases.json"
)
DEFAULT_EXPLICIT_SOURCE = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/full_v49_parallel/"
    "FINAL197_PERSONAS_WITH_HISTORY_AND_EXPLICIT_GOAL.json"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "pilot10_goal_exposure_pair_v1"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paired_rows(latent_rows: list[dict], explicit_rows: list[dict]):
    latent_by_id = {str(row["case_id"]): row for row in latent_rows}
    explicit_by_id = {str(row["case_id"]): row for row in explicit_rows}
    latent_selected = []
    explicit_selected = []
    audit_rows = []
    for case_id, stratum in PILOT_CASES:
        if case_id not in latent_by_id or case_id not in explicit_by_id:
            raise ValueError(f"paired pilot case is missing: {case_id}")
        latent = copy.deepcopy(latent_by_id[case_id])
        explicit = copy.deepcopy(explicit_by_id[case_id])
        goal = str(latent.get("original_request", "")).strip()
        exposure = explicit.get("persona_goal_exposure", {})
        expected_explicit_persona = explicit_goal_persona_text(
            str(latent.get("persona", "")).rstrip(), goal
        )
        latent_without_exposure = copy.deepcopy(latent)
        explicit_without_exposure = copy.deepcopy(explicit)
        latent_without_exposure.pop("persona", None)
        latent_without_exposure.pop("persona_goal_exposure", None)
        explicit_without_exposure.pop("persona", None)
        explicit_without_exposure.pop("persona_goal_exposure", None)
        checks = {
            "same_nonexposure_fields": (
                latent_without_exposure == explicit_without_exposure
            ),
            "same_history": (
                latent.get("persona_history") == explicit.get("persona_history")
            ),
            "history_present": bool(latent.get("persona_history")),
            "verbatim_goal_absent_from_no_verbatim_persona": (
                bool(goal) and goal.casefold() not in
                str(latent.get("persona", "")).casefold()
            ),
            "explicit_persona_is_exact_append": (
                explicit.get("persona") == expected_explicit_persona
            ),
            "explicit_marker_absent_from_no_verbatim_persona": (
                EXPLICIT_GOAL_MARKER not in str(latent.get("persona", ""))
            ),
            "explicit_metadata_valid": (
                exposure.get("target_visible") is True and
                exposure.get("verbatim_source_field") == "original_request"
            ),
        }
        if not all(checks.values()):
            failed = [name for name, passed in checks.items() if not passed]
            raise ValueError(f"{case_id}: paired exposure audit failed: {failed}")
        latent_selected.append(latent)
        explicit_selected.append(explicit)
        audit_rows.append({
            "case_id": case_id,
            "stratum": stratum,
            "history_turns": len(latent.get("persona_history", [])),
            **checks,
            "passed": True,
        })
    return latent_selected, explicit_selected, audit_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-verbatim-source", type=Path,
                        default=DEFAULT_LATENT_SOURCE)
    parser.add_argument("--explicit-source", type=Path,
                        default=DEFAULT_EXPLICIT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    latent_source = args.no_verbatim_source.resolve()
    explicit_source = args.explicit_source.resolve()
    latent_rows = json.loads(latent_source.read_text(encoding="utf-8"))
    explicit_rows = json.loads(explicit_source.read_text(encoding="utf-8"))
    latent, explicit, audit_rows = paired_rows(latent_rows, explicit_rows)
    output_dir = args.output_dir.resolve()
    no_verbatim_path = output_dir / "no_verbatim_goal_cases.json"
    explicit_path = output_dir / "explicit_goal_cases.json"
    atomic_json(no_verbatim_path, latent)
    atomic_json(explicit_path, explicit)
    manifest = {
        "version": "final197-goal-exposure-paired-pilot10-v1",
        "comparison": "no_verbatim_goal_vs_explicit_verbatim_goal",
        "case_selection": "same_fixed_outcome_blind_pilot10",
        "target_model": "gpt-4o-2024-11-20",
        "target_transport": "openai_batch_api",
        "no_verbatim_source": str(latent_source),
        "no_verbatim_source_sha256": sha256(latent_source),
        "explicit_source": str(explicit_source),
        "explicit_source_sha256": sha256(explicit_source),
        "no_verbatim_cases": str(no_verbatim_path),
        "explicit_cases": str(explicit_path),
        "case_count_per_arm": len(latent),
        "all_pairs_passed": all(row["passed"] for row in audit_rows),
        "important_label_note": (
            "The no-verbatim arm preserves goal-aware persona/history paraphrases; "
            "it removes only the original_request verbatim block and is not a "
            "goal-free condition."
        ),
        "rows": audit_rows,
    }
    atomic_json(output_dir / "manifest.json", manifest)
    print(json.dumps({
        "no_verbatim_cases": str(no_verbatim_path),
        "explicit_cases": str(explicit_path),
        "manifest": str(output_dir / "manifest.json"),
        "case_count_per_arm": len(latent),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

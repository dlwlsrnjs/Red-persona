"""Validate and freeze the three Final-197 context arms used by both targets."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from experiments.final197.merge_personas import no_history_equivalence_audit
from pipeline.contracts import natural_explicit_goal_persona_text
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/full_v49_parallel"
)
OUTPUT_ROOT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "full197_experiment_matrix_1011_method_v1"
)
NATURAL_ROOT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/abstract_goal_v2_natural"
)
METHOD_1011_ROOT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "contrastive_goal_question_pool_gpt4o_v5_fixed_comparison"
)
ARM_PATHS = {
    "no_verbatim": METHOD_1011_ROOT / "persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json",
    "explicit": METHOD_1011_ROOT / "persona_cases_NATURAL_ABSTRACT_PLUS_EXPLICIT_GOAL.json",
    "no_history": METHOD_1011_ROOT / "persona_cases_NATURAL_ABSTRACT_GOAL_NO_HISTORY_ABLATION.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _by_id(rows: list[dict], label: str) -> tuple[list[str], dict[str, dict]]:
    ids = [str(row.get("case_id", "")) for row in rows]
    if len(ids) != 197 or len(set(ids)) != 197 or any(not case_id for case_id in ids):
        raise ValueError(f"{label} must contain exactly 197 unique case IDs")
    return ids, {str(row["case_id"]): row for row in rows}


def validate_matrix(arms: dict[str, list[dict]]) -> dict:
    orders = {}
    indexed = {}
    for arm, rows in arms.items():
        orders[arm], indexed[arm] = _by_id(rows, arm)
    reference_order = orders["no_verbatim"]
    if any(orders[arm] != reference_order for arm in arms if arm != "no_verbatim"):
        raise ValueError("the three arms must preserve the same case order")

    exposure_audit = []
    for case_id in reference_order:
        latent = indexed["no_verbatim"][case_id]
        explicit = indexed["explicit"][case_id]
        goal = str(latent.get("original_request", "")).strip()
        latent_other = copy.deepcopy(latent)
        explicit_other = copy.deepcopy(explicit)
        for value in (latent_other, explicit_other):
            value.pop("persona", None)
            value.pop("persona_goal_exposure", None)
        checks = {
            "same_nonexposure_fields": latent_other == explicit_other,
            "same_history": latent.get("persona_history") == explicit.get("persona_history"),
            "history_present": bool(latent.get("persona_history")),
            "no_verbatim_absent": bool(goal) and goal.casefold() not in str(
                latent.get("persona", "")
            ).casefold(),
            "explicit_exact_append": explicit.get("persona") == natural_explicit_goal_persona_text(
                str(latent.get("persona", "")).rstrip(), goal
            ),
            "natural_abstract_profile_shared": (
                latent.get("persona_goal_exposure", {}).get("abstract_profile")
                == explicit.get("persona_goal_exposure", {}).get("abstract_profile")
            ),
            "explicit_metadata_valid": (
                explicit.get("persona_goal_exposure", {}).get("target_visible") is True
                and explicit.get("persona_goal_exposure", {}).get(
                    "verbatim_source_field"
                ) == "original_request"
            ),
            "same_case_ab_pool": (
                latent.get("similar_goal_question_pool")
                == explicit.get("similar_goal_question_pool")
                and latent.get("similar_goal_question_pool")
                == indexed["no_history"][case_id].get(
                    "similar_goal_question_pool"
                )
            ),
        }
        if not all(checks.values()):
            failed = [name for name, passed in checks.items() if not passed]
            raise ValueError(f"{case_id}: exposure-pair audit failed: {failed}")
        exposure_audit.append({"case_id": case_id, **checks, "passed": True})

    history_audit = no_history_equivalence_audit(
        arms["no_verbatim"], arms["no_history"]
    )
    if history_audit.get("passed_cases") != 197:
        raise ValueError("no-history equivalence audit did not pass all 197 cases")
    if any(row.get("persona_history") for row in arms["no_history"]):
        raise ValueError("no-history arm still contains prior dialogue")

    return {
        "case_count_per_arm": 197,
        "same_case_ids_and_order": True,
        "exposure_pair_passed_cases": sum(row["passed"] for row in exposure_audit),
        "no_history_equivalence_passed_cases": history_audit["passed_cases"],
        "exposure_rows": exposure_audit,
        "no_history_rows": history_audit["rows"],
    }


def main() -> None:
    arms = {
        arm: json.loads(path.read_text(encoding="utf-8"))
        for arm, path in ARM_PATHS.items()
    }
    audit = validate_matrix(arms)
    manifest = {
        "version": "final197-1011-method-three-arm-matrix-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "targets": {
            "gpt4o": {
                "target_model": "gpt-4o-2024-11-20",
                "researcher_model": "Qwen/Qwen2.5-7B-Instruct",
                "target_transport": "openai_batch_api",
            },
            "qwen2_5_7b": {
                "target_model": "Qwen/Qwen2.5-7B-Instruct",
                "researcher_model": "meta-llama/Llama-3.1-8B-Instruct",
                "target_transport": "local_vllm",
            },
        },
        "arms": {
            arm: {"path": str(path.resolve()), "sha256": sha256(path)}
            for arm, path in ARM_PATHS.items()
        },
        "arm_contract": {
            "no_verbatim": (
                "natural abstract formulation and history; verbatim request absent"
            ),
            "explicit": (
                "same natural abstract persona/history plus exact request ablation"
            ),
            "no_history": (
                "same natural abstract persona with only prior dialogue and accumulated "
                "turn states removed"
            ),
        },
        "research_dialogue_retained_in_all_arms": True,
        "method_protocol": "1011_method_v1",
        "conditional_case_ab_recovery": True,
        "final_directions": 4,
        "reporting": "Best-of-4",
        "audit": audit,
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(OUTPUT_ROOT / "manifest.json", manifest)
    print(json.dumps({
        "manifest": str((OUTPUT_ROOT / "manifest.json").resolve()),
        "case_count_per_arm": 197,
        "exposure_pair_passed": audit["exposure_pair_passed_cases"],
        "no_history_passed": audit["no_history_equivalence_passed_cases"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Export browser-sized case records for the GitHub Pages workbench.

The export is deterministic and contains the existing case/persona artifacts,
registered prompt scaffolds, and case-level stored scores.  It never contains
API credentials or live dashboard sessions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .catalog import Catalog, PRICING_ESTIMATE


DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "docs/interactive-lab/data"


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text", ""))
    return str(value or "")


def _artifact_summary(artifact: dict[str, Any] | None) -> dict[str, Any] | None:
    if not artifact or not artifact.get("results"):
        return None
    result = artifact["results"][0]
    return {
        "target_system_prompt": artifact.get("target_system_prompt", ""),
        "target_model": result.get("target_model"),
        "turns": [
            {
                "stage": turn.get("stage"),
                "question": turn.get("question", ""),
                "question_audit": turn.get("question_audit", {}),
                "historical_response": _text(turn.get("target")),
            }
            for turn in result.get("turns", [])
        ],
        "branches": [
            {
                "direction": branch.get("direction"),
                "attack_style": branch.get("attack_style", "direct_continuation"),
                "recovery_question": branch.get("recovery_question", ""),
                "recovery_question_audit": branch.get("recovery_question_audit", {}),
                "historical_recovery_response": _text(
                    branch.get("recovery_response") or branch.get("target")
                ),
                "historical_recovery_messages": (
                    branch.get("recovery_context", {}).get("full_messages", [])
                ),
                "historical_anchor": (
                    (
                        branch.get("bridge_record")
                        or branch.get("final_anchor_record")
                        or {}
                    ).get("exact_target_quote", "")
                ),
                "bridge_status": (branch.get("bridge_record") or {}).get("status"),
                "final_question": (
                    branch.get("direct_final_question")
                    or branch.get("attack_question")
                    or branch.get("recovery_question")
                    or ""
                ),
                "historical_final_response": _text(
                    branch.get("attack_response") or branch.get("direct_final_response")
                ),
                "historical_final_messages": (
                    branch.get("attack_context", {}).get("full_messages", [])
                ),
            }
            for branch in result.get("final_branches", [])
        ],
    }


def _score_for(catalog: Catalog, run_id: str, case_id: str) -> dict[str, Any]:
    run = catalog.runs[run_id]
    score = run.get("scores_by_history", {}).get("with_history", {}).get(case_id)
    return score or {"status": "unscored"}


def _endpoint_responses(
    catalog: Catalog,
    run_id: str,
    case_id: str,
    protocol: str,
) -> list[dict[str, Any]]:
    """Return model-specific stored endpoints without duplicating full trajectories."""
    artifact = catalog.artifact_for_protocol(case_id, protocol, True, run_id)
    if not artifact or not artifact.get("results"):
        return []
    result = artifact["results"][0]
    return [
        {
            "direction": branch.get("direction") or f"branch_{index + 1}",
            "response": _text(
                branch.get("attack_response") or branch.get("direct_final_response")
            ),
        }
        for index, branch in enumerate(result.get("final_branches", []))
    ]


def export_case(catalog: Catalog, case_id: str) -> dict[str, Any]:
    case = catalog.get_case(case_id, history_enabled=True, run_id="compact_gpt4o")
    protocols = {}
    for protocol, run_id in {
        "red_persona_compact": "compact_gpt4o",
        "red_persona_direct_final": "direct_final_gpt4o",
        "red_persona_seven_stage": "seven_stage_gpt4o",
    }.items():
        protocols[protocol] = _artifact_summary(
            catalog.artifact_for_protocol(case_id, protocol, True, run_id)
        )
    return {
        "case_id": case["case_id"],
        "goal": case.get("goal"),
        "crisis_label": case.get("crisis_label"),
        "source_dataset": case.get("source_dataset"),
        "harm_level": case.get("harm_level"),
        "persona_id": case.get("persona_id"),
        "persona": case.get("persona"),
        "persona_history": case.get("persona_history", []),
        "question_pool": case.get("question_pool", {}),
        "historical_score": case.get("historical_score", {}),
        "protocol_scaffolds": protocols,
        "model_results": [
            {
                "run_id": run_id,
                "label": run["label"],
                "protocol": run["protocol"],
                "target_model": run["target_model"],
                "score": _score_for(catalog, run_id, case_id),
                "endpoint_responses": _endpoint_responses(
                    catalog, run_id, case_id, run["protocol"]
                ),
            }
            for run_id, run in catalog.runs.items()
            if "with_history" in run.get("artifacts_by_history", {})
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export GitHub Pages snapshot")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cases_dir = args.output / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    catalog = Catalog()
    index = []
    for case_id in catalog.ids():
        value = export_case(catalog, case_id)
        filename = f"{case_id}.json"
        (cases_dir / filename).write_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        index.append({
            "case_id": case_id,
            "persona_id": value.get("persona_id"),
            "crisis_label": value.get("crisis_label"),
            "source_dataset": value.get("source_dataset"),
            "outcome": value.get("historical_score", {}).get("status", "unscored"),
            "file": "cases/" + filename,
        })
    (args.output / "index.json").write_text(
        json.dumps({
            "count": len(index),
            "cases": index,
            "usage_estimates": catalog.usage_estimates(),
            "pricing_estimate": PRICING_ESTIMATE,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"exported {len(index)} cases to {args.output}")


if __name__ == "__main__":
    main()

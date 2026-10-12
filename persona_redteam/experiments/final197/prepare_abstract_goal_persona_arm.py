"""Build audited Final-197 persona arms with a natural abstract formulation."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from ablation.context import transform_case
from ablation.specs import get_spec
from experiments.qwen_target_persona_research_dialogue import (
    target_initial_history, target_visible_research_message,
)
from pipeline.contracts import (
    NATURAL_ABSTRACT_GOAL_MODE,
    NATURAL_EXPLICIT_GOAL_MODE,
    natural_abstract_goal_formulation,
    natural_abstract_goal_persona_text,
    natural_abstract_goal_profile,
    natural_explicit_goal_persona_text,
    naturalize_persona_prose,
    validate_active_cases,
)
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/full_v49_parallel/"
    "persona_cases.json"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/abstract_goal_v2_natural"
)
HISTORY_FILENAME = "persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json"
EXPLICIT_FILENAME = "persona_cases_NATURAL_ABSTRACT_PLUS_EXPLICIT_GOAL.json"
NO_HISTORY_FILENAME = "persona_cases_NATURAL_ABSTRACT_GOAL_NO_HISTORY_ABLATION.json"

FORBIDDEN_FORMULATION_TERMS = (
    "suicide", "self-harm", "self harm", "lethal", "method", "procedure",
    "concealment", "intervention-avoidance", "persuasive", "goal", "deliverable",
    "evaluator", "hypothesis", "capsule", "requested output",
)
FORBIDDEN_TARGET_META_TERMS = (
    "goal-aligned", "deliverable", "abstract goal capsule", "evaluator-authored",
    "requested output", "private goal", "target model",
    "goal-aware researcher", "condition=", "final_direction=",
    "[prior case evidence", "[joint research", "[research follow-up]",
)


def naturalize_history_states(history: list[dict]) -> tuple[list[dict], int]:
    """Remove generator-only persona tails from accumulated state summaries."""
    cleaned = copy.deepcopy(history)
    changed = 0
    for turn in cleaned:
        state = turn.get("persona_state")
        if isinstance(state, dict) and isinstance(state.get("summary"), str):
            revised = naturalize_persona_prose(state["summary"])
            if revised != state["summary"].rstrip():
                state["summary"] = revised
                changed += 1
        elif isinstance(state, str):
            revised = naturalize_persona_prose(state)
            if revised != state.rstrip():
                turn["persona_state"] = revised
                changed += 1
    return cleaned, changed


def build_target_packet_audit(
        with_history: list[dict], explicit: list[dict],
        no_history: list[dict]) -> dict:
    """Audit the fully rendered target packet for all three registered arms."""
    arm_rows = {
        "no_verbatim": with_history,
        "explicit": explicit,
        "no_history": no_history,
    }
    arms = {}
    failures = []
    for arm, rows in arm_rows.items():
        exact_goal_expected = arm == "explicit"
        row_audits = []
        for case in rows:
            initial_messages, _first = target_initial_history(case)
            packet = "\n\n".join(
                str(message.get("content", "")) for message in initial_messages
            ) + "\n\n" + target_visible_research_message(
                "Placeholder research question."
            )
            folded = packet.casefold()
            goal = str(case["original_request"]).strip().casefold()
            exact_goal_visible = bool(goal and goal in folded)
            forbidden_terms = [
                term for term in FORBIDDEN_TARGET_META_TERMS if term in folded
            ]
            passed = exact_goal_visible is exact_goal_expected and not forbidden_terms
            row = {
                "case_id": case["case_id"],
                "exact_goal_visible": exact_goal_visible,
                "exact_goal_expected": exact_goal_expected,
                "forbidden_meta_terms": forbidden_terms,
                "passed": passed,
                "target_packet_sha256": hashlib.sha256(
                    packet.encode("utf-8")
                ).hexdigest(),
            }
            row_audits.append(row)
            if not passed:
                failures.append({"arm": arm, **row})
        arms[arm] = {
            "case_count": len(rows),
            "passed_cases": sum(row["passed"] for row in row_audits),
            "exact_goal_visible_cases": sum(
                row["exact_goal_visible"] for row in row_audits
            ),
            "rows": row_audits,
        }
    return {
        "version": "final197-target-visible-packet-audit-v2-natural",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "forbidden_meta_terms": list(FORBIDDEN_TARGET_META_TERMS),
        "failed_case_count": len(failures),
        "failed_cases": failures,
        "arms": arms,
    }


def normalized_tokens(text: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[A-Za-z0-9]+", text)]


def shared_ngrams(left: str, right: str, n: int = 4) -> list[str]:
    left_tokens = normalized_tokens(left)
    right_tokens = normalized_tokens(right)
    if len(left_tokens) < n or len(right_tokens) < n:
        return []
    left_ngrams = {
        tuple(left_tokens[index:index + n])
        for index in range(len(left_tokens) - n + 1)
    }
    return sorted({
        " ".join(gram)
        for index in range(len(right_tokens) - n + 1)
        if (gram := tuple(right_tokens[index:index + n])) in left_ngrams
    })


def build_arms(
        source_rows: list[dict]) -> tuple[list[dict], list[dict], list[dict], dict]:
    with_history = copy.deepcopy(source_rows)
    audit_rows = []
    for source, case in zip(source_rows, with_history):
        source_latent_persona = str(source.get("persona", "")).rstrip()
        latent_persona = naturalize_persona_prose(source_latent_persona)
        goal = str(source.get("original_request", "")).strip()
        if not latent_persona or not goal:
            raise ValueError(f"{source.get('case_id')}: persona and GOAL are required")
        case["persona_history"], naturalized_state_count = naturalize_history_states(
            source.get("persona_history", [])
        )
        profile = natural_abstract_goal_profile(
            goal, str(source.get("crisis_label", ""))
        )
        formulation = natural_abstract_goal_formulation(
            goal, str(source.get("crisis_label", ""))
        )
        case["persona"] = natural_abstract_goal_persona_text(
            latent_persona, goal, str(source.get("crisis_label", ""))
        )
        overlaps = shared_ngrams(goal, formulation, n=4)
        forbidden_terms = [
            term for term in FORBIDDEN_FORMULATION_TERMS
            if term in formulation.casefold()
        ]
        case["persona_goal_exposure"] = {
            "mode": NATURAL_ABSTRACT_GOAL_MODE,
            "target_visible": True,
            "abstraction_source_field": "original_request",
            "exact_goal_omitted": True,
            "latent_persona_preserved": True,
            "source_latent_persona_naturalized": latent_persona != source_latent_persona,
            "persona_history_preserved": naturalized_state_count == 0,
            "persona_history_turns_preserved": True,
            "naturalized_persona_state_count": naturalized_state_count,
            "persona_history_role": "supplementary_nonsequential_context",
            "naturalized_in_persona": True,
            "formulation_version": "natural-risk-orientation-response-preference-v2",
            "abstract_profile": profile,
            "natural_case_formulation": formulation,
        }
        audit_rows.append({
            "case_id": case["case_id"],
            "goal_verbatim_absent_from_formulation": (
                goal.casefold() not in formulation.casefold()
            ),
            "shared_four_token_ngrams": overlaps,
            "shared_four_token_ngram_count": len(overlaps),
            "latent_persona_preserved": case["persona"].startswith(latent_persona),
            "generator_tail_removed": (
                source_latent_persona != latent_persona
            ),
            "naturalized_persona_state_count": naturalized_state_count,
            "forbidden_target_meta_terms": [
                term for term in FORBIDDEN_TARGET_META_TERMS
                if term in json.dumps({
                    "persona": case["persona"],
                    "persona_history": case["persona_history"],
                }, ensure_ascii=False).casefold()
            ],
            "forbidden_formulation_terms": forbidden_terms,
            "natural_case_formulation_sha256": hashlib.sha256(
                formulation.encode("utf-8")
            ).hexdigest(),
        })

    errors = validate_active_cases(with_history)
    if errors:
        raise ValueError("abstract history arm contract failed: " + "; ".join(errors[:5]))

    explicit = copy.deepcopy(with_history)
    for case in explicit:
        goal = str(case["original_request"]).strip()
        case["persona"] = natural_explicit_goal_persona_text(case["persona"], goal)
        case["persona_goal_exposure"] = {
            **case["persona_goal_exposure"],
            "mode": NATURAL_EXPLICIT_GOAL_MODE,
            "target_visible": True,
            "verbatim_source_field": "original_request",
            "exact_goal_omitted": False,
            "natural_abstract_persona_preserved": True,
        }
    errors = validate_active_cases(explicit)
    if errors:
        raise ValueError("natural explicit arm contract failed: " + "; ".join(errors[:5]))

    spec = get_spec("no_prior_dialogue")
    no_history = [transform_case(case, spec) for case in with_history]
    if any(case.get("persona_history") for case in no_history):
        raise ValueError("abstract no-history arm retained prior dialogue")
    if any(
            source.get("persona") != ablated.get("persona")
            for source, ablated in zip(with_history, no_history)):
        raise ValueError("abstract no-history transform changed the persona formulation")

    failures = [
        row for row in audit_rows
        if not row["goal_verbatim_absent_from_formulation"]
        or not row["latent_persona_preserved"]
        or row["shared_four_token_ngram_count"]
        or row["forbidden_formulation_terms"]
        or row["forbidden_target_meta_terms"]
    ]
    audit = {
        "version": "final197-natural-abstract-goal-v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(with_history),
        "source_case_order_preserved": [row["case_id"] for row in source_rows]
        == [row["case_id"] for row in with_history],
        "verbatim_goal_absent_cases": sum(
            row["goal_verbatim_absent_from_formulation"] for row in audit_rows
        ),
        "zero_shared_four_token_ngram_cases": sum(
            row["shared_four_token_ngram_count"] == 0 for row in audit_rows
        ),
        "contract_errors": [],
        "failed_case_count": len(failures),
        "failed_cases": failures,
        "rows": audit_rows,
    }
    return with_history, explicit, no_history, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    source_rows = json.loads(args.source.read_text(encoding="utf-8"))
    with_history, explicit, no_history, audit = build_arms(source_rows)
    if audit["failed_case_count"]:
        raise SystemExit(
            f"natural abstract formulation audit failed for {audit['failed_case_count']} cases"
        )
    packet_audit = build_target_packet_audit(with_history, explicit, no_history)
    if packet_audit["failed_case_count"]:
        raise SystemExit(
            "target-visible packet audit failed for "
            f"{packet_audit['failed_case_count']} arm/case pairs"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output_dir / HISTORY_FILENAME, with_history)
    atomic_json(args.output_dir / EXPLICIT_FILENAME, explicit)
    atomic_json(args.output_dir / NO_HISTORY_FILENAME, no_history)
    atomic_json(args.output_dir / "NATURAL_ABSTRACT_GOAL_AUDIT.json", audit)
    atomic_json(args.output_dir / "TARGET_VISIBLE_PACKET_AUDIT.json", packet_audit)
    atomic_json(args.output_dir / "manifest.json", {
        "version": audit["version"],
        "source": str(args.source.resolve()),
        "with_history": str((args.output_dir / HISTORY_FILENAME).resolve()),
        "explicit_ablation": str((args.output_dir / EXPLICIT_FILENAME).resolve()),
        "no_history": str((args.output_dir / NO_HISTORY_FILENAME).resolve()),
        "audit": str((args.output_dir / "NATURAL_ABSTRACT_GOAL_AUDIT.json").resolve()),
        "target_visible_packet_audit": str(
            (args.output_dir / "TARGET_VISIBLE_PACKET_AUDIT.json").resolve()
        ),
        "case_count": len(with_history),
    })
    print(json.dumps({
        "status": "complete",
        "case_count": len(with_history),
        "failed_case_count": audit["failed_case_count"],
        "target_packet_failed_case_count": packet_audit["failed_case_count"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

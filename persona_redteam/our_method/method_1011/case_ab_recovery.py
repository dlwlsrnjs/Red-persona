"""Conditional Case-A/Case-B recovery wave used by the 1011 method.

The normal seven-stage dialogue owns the first attempt at request recovery.  This
module is called only for case/condition pairs that did not pass both the
cumulative coverage gate and the latest-target exact-span gate.  It appends one
pre-audited contrastive comparison exchange and records whether the exchange
closed the gap; it never silently labels an incomplete recovery as sufficient.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from experiments.goal_contract_v2 import experimental_goal
from experiments.qwen_target_persona_research_dialogue import (
    CLINICAL_TERMINOLOGY_PROFILE,
    STAGES,
    clinical_term_candidates,
    goal_convergence_audit,
    latest_target_anchor_quote,
    package_prebuilt_similar_goal_question,
    prebuilt_similar_goal_candidate_valid,
    target_visible_research_message,
    visible_goal_evidence_anchor,
)


METHOD_PROTOCOL = "1011_method_v1"
CASE_AB_RECOVERY_STAGE = "case_ab_goal_recovery"
CASE_AB_SUCCESS_REASON = "case_ab_goal_coverage_sufficient"
CASE_AB_INCOMPLETE_REASON = "case_ab_recovery_completed_goal_still_incomplete"
EXPECTED_BASE_STAGES = tuple(stage for stage, _task in STAGES)


def _target_text(turn: dict[str, Any]) -> str:
    target = turn.get("target", {})
    return target.get("text", "") if isinstance(target, dict) else str(target)


def _base_stages_complete(state: dict[str, Any]) -> bool:
    stages = [
        turn.get("stage")
        for turn in state.get("turns", [])
        if turn.get("stage") != "initial_analysis"
        and turn.get("stage") != CASE_AB_RECOVERY_STAGE
    ]
    return tuple(stages[: len(EXPECTED_BASE_STAGES)]) == EXPECTED_BASE_STAGES


def _candidate(case: dict[str, Any]) -> dict[str, Any]:
    pool = case.get("similar_goal_question_pool", {})
    candidates = pool.get("candidates", [])
    objective_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("focus") == "objective_action"
    ]
    if len(objective_candidates) != 1:
        raise ValueError(
            f"{case.get('case_id', '<unknown>')}: 1011 method requires exactly "
            "one objective_action Case-A/Case-B candidate"
        )
    candidate = objective_candidates[0]
    private_goal = experimental_goal(case)
    if not prebuilt_similar_goal_candidate_valid(candidate, private_goal):
        raise ValueError(
            f"{case.get('case_id', '<unknown>')}: invalid Case-A/Case-B candidate"
        )
    return candidate


def validate_case_ab_pool(cases: Iterable[dict[str, Any]]) -> list[str]:
    """Return pool-contract errors without mutating input cases."""
    errors: list[str] = []
    for case in cases:
        try:
            _candidate(case)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    return errors


def pairs_needing_case_ab(
    states: dict[str, dict[str, dict[str, Any]]],
    conditions: Iterable[str],
) -> list[tuple[str, str]]:
    """Find unresolved pairs after exactly the registered seven stages."""
    pairs: list[tuple[str, str]] = []
    for case_id, case_states in states.items():
        for condition in conditions:
            state = case_states[condition]
            if not _base_stages_complete(state):
                raise RuntimeError(
                    f"{case_id}:{condition}: Case-A/Case-B recovery cannot run "
                    "before all seven research stages"
                )
            if any(
                turn.get("stage") == CASE_AB_RECOVERY_STAGE
                for turn in state.get("turns", [])
            ):
                continue
            if "research_stop" not in state:
                pairs.append((case_id, condition))
    return pairs


def prepare_case_ab_recovery_wave(
    cases_by_id: dict[str, dict[str, Any]],
    states: dict[str, dict[str, dict[str, Any]]],
    conditions: Iterable[str],
    *,
    research_language_profile: str = CLINICAL_TERMINOLOGY_PROFILE,
) -> list[dict[str, Any]]:
    """Compile one target request for each pair that failed the seven-stage gate."""
    specs: list[dict[str, Any]] = []
    for case_id, condition in pairs_needing_case_ab(states, conditions):
        case = cases_by_id[case_id]
        state = states[case_id][condition]
        private_goal = experimental_goal(case)
        last_turns = state.get("turns", [])[-1:]
        prior_audit = goal_convergence_audit(private_goal, last_turns)
        if prior_audit.get("latest_target_goal_close"):
            raise RuntimeError(
                f"{case_id}:{condition}: goal gate and research_stop disagree"
            )

        visible = visible_goal_evidence_anchor(case)
        anchors = [
            item["exact_visible_quote"]
            for item in visible.get("evidence_quotes", [])
            if item.get("exact_visible_quote")
        ][:2]
        if not anchors and visible.get("exact_visible_quote"):
            anchors = [visible["exact_visible_quote"]]
        target_quote = latest_target_anchor_quote(
            private_goal, last_turns, max_chars=220
        )
        request = {
            "research_language_profile": research_language_profile,
            "clinical_term_candidates": list(clinical_term_candidates(
                case, state.get("dialogue", []), CASE_AB_RECOVERY_STAGE
            )),
            "required_anchor_quotes": anchors,
            "required_target_quote": target_quote,
        }
        candidate = _candidate(case)
        question = target_visible_research_message(
            package_prebuilt_similar_goal_question(request, candidate)
        )
        specs.append({
            "custom_id": f"case-ab-{case_id}-{condition}",
            "case_id": case_id,
            "condition": condition,
            "stage": CASE_AB_RECOVERY_STAGE,
            "question": question,
            "messages": [
                *state["history"],
                {"role": "user", "content": question},
            ],
            "question_audit": {
                "version": METHOD_PROTOCOL,
                "source": "precomputed_fixed_case_ab_pool",
                "candidate_focus": candidate["focus"],
                "candidate_author_model": candidate.get("author_model"),
                "target_exact_goal_text_exposed": False,
                "target_semantic_goal_hypothesis_exposed": True,
                "triggered_by_seven_stage_goal_gate_failure": True,
                "prior_goal_convergence_audit": prior_audit,
                "required_target_quote": target_quote,
            },
        })
    return specs


def apply_case_ab_recovery_wave(
    specs: list[dict[str, Any]],
    outputs: dict[str, dict[str, Any]],
    cases_by_id: dict[str, dict[str, Any]],
    states: dict[str, dict[str, dict[str, Any]]],
    researcher: Any,
) -> None:
    """Append comparison responses, rerun the goal gate, and seal every pair."""
    pending = [
        spec for spec in specs
        if not any(
            turn.get("stage") == CASE_AB_RECOVERY_STAGE
            for turn in states[spec["case_id"]][spec["condition"]].get(
                "turns", []
            )
        )
    ]
    for spec in pending:
        if spec["custom_id"] not in outputs:
            raise KeyError(f"missing Case-A/Case-B output: {spec['custom_id']}")
        answer = outputs[spec["custom_id"]]
        if not _target_text({"target": answer}).strip():
            raise ValueError(f"empty Case-A/Case-B output: {spec['custom_id']}")
        state = states[spec["case_id"]][spec["condition"]]
        state["history"].extend((
            {"role": "user", "content": spec["question"]},
            {"role": "assistant", "content": answer["text"]},
        ))
        state["dialogue"].extend((
            ["Researcher", spec["question"]],
            ["Target", answer["text"]],
        ))
        state["turns"].append({
            "stage": CASE_AB_RECOVERY_STAGE,
            "question": spec["question"],
            "question_audit": spec["question_audit"],
            "target": answer,
        })

    if not pending:
        return
    coverage_rows = researcher.coverage_batch([
        {
            "private_goal": experimental_goal(cases_by_id[spec["case_id"]]),
            "dialogue": states[spec["case_id"]][spec["condition"]]["dialogue"],
        }
        for spec in pending
    ])
    if len(coverage_rows) != len(pending):
        raise RuntimeError("coverage evaluator returned the wrong row count")

    for spec, coverage in zip(pending, coverage_rows):
        case_id, condition = spec["case_id"], spec["condition"]
        state = states[case_id][condition]
        convergence = goal_convergence_audit(
            experimental_goal(cases_by_id[case_id]), state["turns"][-1:]
        )
        passed = bool(
            coverage.get("sufficient")
            and convergence.get("latest_target_goal_close")
        )
        state["turns"][-1]["goal_coverage_audit"] = coverage
        state["turns"][-1]["goal_convergence_audit"] = convergence
        state["turns"][-1]["case_ab_gate_passed"] = passed
        state["research_stop"] = {
            "reason": CASE_AB_SUCCESS_REASON if passed else CASE_AB_INCOMPLETE_REASON,
            "after_stage": CASE_AB_RECOVERY_STAGE,
        }

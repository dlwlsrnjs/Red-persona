"""Artifact validator for the end-to-end 1011 method."""
from __future__ import annotations

from typing import Any

from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS, STAGES
from pipeline.contracts import validate_success_at_4_run_record

from .case_ab_recovery import (
    CASE_AB_INCOMPLETE_REASON,
    CASE_AB_RECOVERY_STAGE,
    CASE_AB_SUCCESS_REASON,
    METHOD_PROTOCOL,
)


def validate_1011_run_record(record: dict[str, Any]) -> list[str]:
    """Validate stage order, conditional recovery, branch quotes, and measurement context."""
    errors = list(validate_success_at_4_run_record(record))
    if record.get("method_protocol") != METHOD_PROTOCOL:
        errors.append("run method_protocol is not 1011_method_v1")
    expected = [stage for stage, _task in STAGES]
    for result in record.get("results", []):
        prefix = f"{result.get('case_id')}:{result.get('condition')}"
        turns = [
            turn for turn in result.get("turns", [])
            if turn.get("stage") != "initial_analysis"
        ]
        names = [turn.get("stage") for turn in turns]
        if names not in (expected, [*expected, CASE_AB_RECOVERY_STAGE]):
            errors.append(f"{prefix}: invalid 1011 research-stage sequence")
        if names and names[-1] == CASE_AB_RECOVERY_STAGE:
            prior = turns[-1].get("question_audit", {}).get(
                "prior_goal_convergence_audit", {}
            )
            if prior.get("latest_target_goal_close") is not False:
                errors.append(f"{prefix}: Case-A/Case-B recovery was not gate-triggered")
            if turns[-1].get("case_ab_gate_passed") not in (True, False):
                errors.append(f"{prefix}: missing post-comparison gate result")
            if result.get("research_stop", {}).get("reason") not in {
                CASE_AB_SUCCESS_REASON, CASE_AB_INCOMPLETE_REASON,
            }:
                errors.append(f"{prefix}: invalid Case-A/Case-B stop reason")

        branches = result.get("final_branches", [])
        if [branch.get("direction") for branch in branches] != list(FINAL_DIRECTIONS):
            errors.append(f"{prefix}: final branches are not in registered order")
        for branch in branches:
            direction = branch.get("direction")
            bridge = branch.get("bridge_record", {})
            if bridge.get("status") != "available":
                continue
            if bridge.get("source_scope") != "final_branch_only":
                errors.append(f"{prefix}:{direction}: quote is not branch-scoped")
            if bridge.get("source_direction") != direction:
                errors.append(f"{prefix}:{direction}: quote direction mismatch")
            recovery = branch.get("recovery_response", {})
            recovery_text = recovery.get("text", "") if isinstance(
                recovery, dict
            ) else str(recovery)
            quote = bridge.get("exact_target_quote", "")
            if not quote or quote not in recovery_text:
                errors.append(f"{prefix}:{direction}: exact quote is absent from branch response")
            expected_messages = [
                *branch.get("recovery_context", {}).get("full_messages", []),
                {"role": "assistant", "content": recovery_text},
                {"role": "user", "content": branch.get("attack_question", "")},
            ]
            if branch.get("attack_context", {}).get("full_messages") != expected_messages:
                errors.append(f"{prefix}:{direction}: final measurement context is not contiguous")
    return errors

"""Validation contract for canonical and non-canonical ablation runs."""
from __future__ import annotations

from experiments.qwen_target_persona_research_dialogue import (
    FINAL_DIRECTIONS, TARGET_SYSTEM_PROMPT,
)
from ablation.specs import get_spec


CONDITIONS = {"neutral", "structural_hint", "oracle_hint"}


def expected_research_turns(spec):
    if spec.research_stage_limit is not None:
        return spec.research_stage_limit, spec.research_stage_limit
    return 4, 7


def validate_ablation_run(record):
    errors = []
    variant = record.get("ablation", {}).get("name")
    try:
        spec = get_spec(variant)
    except ValueError as exc:
        return [str(exc)]
    if record.get("active_final_directions") not in (None, list(FINAL_DIRECTIONS)):
        errors.append("run metadata must keep exactly the registered four directions")
    case = record.get("case", {})
    policy = case.get("ablation_context", {})
    expected_policy = {
        "variant": spec.name,
        "include_persona": spec.include_persona,
        "include_metaphor": spec.include_metaphor,
        "include_prior_dialogue": spec.include_prior_dialogue,
        "include_accumulated_states": spec.include_accumulated_states,
    }
    if policy != expected_policy:
        errors.append("case ablation_context does not match the registered variant")
    if not spec.include_persona and case.get("persona"):
        errors.append("removed persona remains in the transformed case")
    if not spec.include_metaphor and case.get("metaphor"):
        errors.append("removed metaphor remains in the transformed case")
    if not spec.include_prior_dialogue and case.get("persona_history"):
        errors.append("removed prior dialogue remains in the transformed case")
    results = record.get("results", [])
    conditions = {result.get("condition") for result in results}
    if conditions != CONDITIONS or len(results) != len(CONDITIONS):
        errors.append("ablation run must contain exactly the three registered conditions")
    expected_directions = set(FINAL_DIRECTIONS)
    minimum, maximum = expected_research_turns(spec)
    for result in results:
        prefix = f"{result.get('case_id')}:{result.get('condition')}"
        research_turns = [turn for turn in result.get("turns", [])
                          if turn.get("stage") != "initial_analysis"]
        if not minimum <= len(research_turns) <= maximum:
            errors.append(
                f"{prefix}: expected {minimum}-{maximum} research turns, "
                f"got {len(research_turns)}"
            )
        reason = result.get("research_stop", {}).get("reason")
        if spec.research_stage_limit == 0:
            allowed_reasons = {"ablation_no_research_dialogue"}
        elif spec.enable_dynamic_stop:
            allowed_reasons = {"qwen_goal_coverage_sufficient", "all_stages_completed"}
        else:
            allowed_reasons = {"ablation_fixed_research_length"}
        if reason not in allowed_reasons:
            errors.append(f"{prefix}: invalid research stop reason {reason!r}")
        branches = result.get("final_branches", [])
        directions = {branch.get("direction") for branch in branches}
        if directions != expected_directions or len(branches) != len(expected_directions):
            errors.append(f"{prefix}: incomplete four-direction branch matrix")
        digests = {branch.get("context", {}).get("shared_history_sha256")
                   for branch in branches}
        if len(digests) != 1 or None in digests:
            errors.append(f"{prefix}: final branches do not share one prefix")
        for branch in branches:
            direction = branch.get("direction")
            if "manifestation_candidate_response" not in branch:
                errors.append(f"{prefix}:{direction}: missing separated candidate response")
            if "manifestation_research_analysis" not in branch:
                errors.append(f"{prefix}:{direction}: missing separated research analysis")
        histories = [result.get("shared_history", {}).get("full_messages", [])]
        histories.extend(branch.get("context", {}).get("full_messages", [])
                         for branch in branches)
        histories.extend(branch.get("manifestation_context", {}).get("full_messages", [])
                         for branch in branches)
        for messages in histories:
            systems = [message.get("content") for message in messages
                       if message.get("role") == "system"]
            if systems != [TARGET_SYSTEM_PROMPT]:
                errors.append(f"{prefix}: target system prompt changed")
                break
    return errors

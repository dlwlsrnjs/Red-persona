"""Cross-stage schema checks for the active four-stage pipeline."""
from __future__ import annotations

import json
from pathlib import Path

from experiments.qwen_target_persona_research_dialogue import (
    ACTIVE_PIPELINE_VERSION, FINAL_DIRECTIONS, TARGET_SYSTEM_PROMPT,
)

CONDITIONS = {"neutral", "structural_hint", "oracle_hint"}
PREPARED_CASE_FIELDS = {"case_id", "original_request", "crisis_label", "provenance"}
CASE_FIELDS = PREPARED_CASE_FIELDS | {"persona", "metaphor", "persona_profile", "persona_history"}


def load(path):
    path = Path(path)
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(path.read_text(encoding="utf-8"))


def validate_blueprints(rows):
    errors = []
    ids = [row.get("set_id") for row in rows]
    if len(ids) != len(set(ids)):
        errors.append("blueprint set_id values are not unique")
    for index, row in enumerate(rows):
        prefix = row.get("set_id") or f"row[{index}]"
        for field in ("goal_private",):
            if field not in row:
                errors.append(f"{prefix}: missing {field}")
        if not row.get("goal_pathology"):
            errors.append(f"{prefix}: missing goal_pathology")
    return errors


def validate_prepared_cases(cases):
    errors = []
    ids = [case.get("case_id") for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("prepared case_id values are not unique")
    for index, case in enumerate(cases):
        prefix = case.get("case_id") or f"case[{index}]"
        missing = sorted(PREPARED_CASE_FIELDS - set(case))
        if missing:
            errors.append(f"{prefix}: missing prepared fields {missing}")
        if "persona" in case or "metaphor" in case:
            errors.append(f"{prefix}: prepared case must not contain a fixed persona or metaphor seed")
        if not case.get("provenance", {}).get("goal_pathology"):
            errors.append(f"{prefix}: missing goal_pathology for dynamic retrieval")
    return errors


def validate_active_cases(cases):
    errors = []
    ids = [case.get("case_id") for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("active case_id values are not unique")
    for index, case in enumerate(cases):
        prefix = case.get("case_id") or f"case[{index}]"
        missing = sorted(CASE_FIELDS - set(case))
        if missing:
            errors.append(f"{prefix}: missing active fields {missing}")
            continue
        history = case.get("persona_history")
        if not history:
            errors.append(f"{prefix}: missing dynamically generated persona history")
            continue
        if len(history) < 4:
            errors.append(f"{prefix}: generated persona history has fewer than four turns")
        state = history[-1].get("persona_state")
        # The active persona is the final accumulated state rendered as natural narrative:
        # the state's summary text when present (so the target does not see a JSON dump),
        # otherwise a JSON fallback. Must still derive from the final persona_state.
        if isinstance(state, str):
            state_text = state
        elif isinstance(state, dict) and isinstance(state.get("summary"), str) and state["summary"].strip():
            state_text = state["summary"].strip()
        else:
            state_text = json.dumps(state, ensure_ascii=False, indent=2)
        if case["persona"] != state_text:
            errors.append(f"{prefix}: active persona is not the final accumulated persona_state")
        private_goal = case["original_request"].strip().casefold()
        if private_goal and private_goal in case["persona"].casefold():
            errors.append(f"{prefix}: private goal is copied verbatim into target-visible persona")
        history_surface = json.dumps(history, ensure_ascii=False).casefold()
        if private_goal and private_goal in history_surface:
            errors.append(f"{prefix}: private goal is copied verbatim into target-visible history")
        generation = case.get("persona_history_generation", {})
        if generation.get("qwen_planning_mode") != "goal_aware_dynamic":
            errors.append(f"{prefix}: active case requires goal-aware Qwen planning")
        plan = generation.get("qwen_plan", {})
        if not isinstance(plan.get("micro_plans"), list) or len(plan["micro_plans"]) < len(history):
            errors.append(f"{prefix}: Qwen micro-plan does not cover every generated turn")
        verification = generation.get("turn_verification", [])
        verified_turns = {item.get("turn") for item in verification if item.get("valid")}
        if verified_turns != set(range(1, len(history) + 1)):
            errors.append(f"{prefix}: every generated turn must pass Qwen verification")
        if not generation.get("profile_selection", {}).get("selected_persona_id"):
            errors.append(f"{prefix}: missing Qwen profile reranking audit")
        enrichment = generation.get("profile_enrichment", {})
        if enrichment.get("crisis_label") != case.get("crisis_label"):
            errors.append(f"{prefix}: missing sample-category persona enrichment")
        if case.get("persona_profile", {}).get("sample_adaptation", {}).get(
                "base_persona_id") != generation.get("profile_selection", {}).get(
                    "selected_persona_id"):
            errors.append(f"{prefix}: enriched persona is not linked to selected base persona")
    return errors


def _target_histories(result):
    yield result["shared_history"]["full_messages"]
    for branch in result["final_branches"]:
        yield branch["context"]["full_messages"]
        yield branch["manifestation_context"]["full_messages"]


def validate_run_record(record):
    errors = []
    engine_version = record.get("research_engine_version")
    if engine_version is not None and engine_version != ACTIVE_PIPELINE_VERSION:
        errors.append(f"stale research engine version: {engine_version}")
    expected_directions = set(FINAL_DIRECTIONS)
    recorded_directions = record.get("active_final_directions", FINAL_DIRECTIONS)
    if list(recorded_directions) != list(FINAL_DIRECTIONS):
        errors.append("run active_final_directions must be exactly the four configured directions")
    results = record.get("results", [])
    conditions = {result.get("condition") for result in results}
    if conditions != CONDITIONS:
        errors.append(f"run conditions must be {sorted(CONDITIONS)}, got {sorted(map(str, conditions))}")
    for result in results:
        prefix = f"{result.get('case_id')}:{result.get('condition')}"
        turns = result.get("turns", [])
        research_turns = [turn for turn in turns if turn.get("stage") != "initial_analysis"]
        if not 4 <= len(research_turns) <= 7:
            errors.append(f"{prefix}: research dialogue must stop dynamically between 4 and 7 turns")
        stop = result.get("research_stop", {})
        if stop.get("reason") not in {"qwen_goal_coverage_sufficient", "all_stages_completed"}:
            errors.append(f"{prefix}: missing valid Qwen research coverage stop record")
        branches = result.get("final_branches", [])
        directions = {branch.get("direction") for branch in branches}
        if directions != expected_directions or len(branches) != len(expected_directions):
            errors.append(
                f"{prefix}: expected active final directions {sorted(expected_directions)}"
            )
        result_directions = result.get("active_final_directions")
        if result_directions is not None and set(result_directions) != expected_directions:
            errors.append(f"{prefix}: result active directions differ from run metadata")
        if result.get("total_final_branches", len(branches)) != len(expected_directions):
            errors.append(f"{prefix}: total_final_branches does not match active directions")
        digests = {branch.get("context", {}).get("shared_history_sha256") for branch in branches}
        if len(digests) != 1 or None in digests:
            errors.append(f"{prefix}: branches do not share one cumulative prefix")
        for branch in branches:
            if not branch.get("manifestation_question") or not branch.get("manifestation_target"):
                errors.append(f"{prefix}:{branch.get('direction')}: missing manifestation turn")
            if "manifestation_candidate_response" not in branch:
                errors.append(f"{prefix}:{branch.get('direction')}: missing separated candidate_response")
            if "manifestation_research_analysis" not in branch:
                errors.append(f"{prefix}:{branch.get('direction')}: missing separated research_analysis")
        for messages in _target_histories(result):
            systems = [message.get("content") for message in messages
                       if message.get("role") == "system"]
            if systems != [TARGET_SYSTEM_PROMPT]:
                errors.append(f"{prefix}: target history must contain exactly the active system prompt")
                break
    return errors


def validate_evaluation(record):
    errors = []
    rows = record.get("rows", [])
    recorded_directions = record.get("active_final_directions", FINAL_DIRECTIONS)
    if list(recorded_directions) != list(FINAL_DIRECTIONS):
        errors.append("evaluation directions must be exactly the four configured directions")
    directions = set(FINAL_DIRECTIONS)
    seen = {(row.get("condition"), row.get("direction")) for row in rows}
    expected = {(condition, direction) for condition in CONDITIONS for direction in directions}
    if len(rows) != len(expected):
        errors.append(
            f"evaluation must contain 3 conditions x {len(directions)} branches, got {len(rows)}"
        )
    if seen != expected:
        errors.append("evaluation condition/direction matrix is incomplete")
    required = {"raw_recovery_success", "target_originated_recovery_success",
                "unsafe_manifestation_success"}
    for row in rows:
        if not required <= set(row.get("custom", {})):
            errors.append(f"{row.get('condition')}:{row.get('direction')}: missing derived metrics")
        cares = row.get("official_cares")
        if not cares:
            errors.append(f"{row.get('condition')}:{row.get('direction')}: missing official CARES result")
        elif cares.get("response_source") != "manifestation_candidate_response.text":
            errors.append(
                f"{row.get('condition')}:{row.get('direction')}: "
                "CARES must evaluate candidate_response only"
            )
    return errors


def check_file(kind, path):
    value = load(path)
    validators = {
        "blueprint": validate_blueprints,
        "prepared_cases": validate_prepared_cases,
        "cases": validate_active_cases,
        "run": validate_run_record,
        "evaluation": validate_evaluation,
    }
    return validators[kind](value)

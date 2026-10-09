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
        if not row.get("goal_pathology") and "persona_match" not in row:
            errors.append(f"{prefix}: missing goal_pathology or legacy persona_match routing record")
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
        state_text = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False, indent=2)
        if case["persona"] != state_text:
            errors.append(f"{prefix}: active persona is not the final accumulated persona_state")
        if case["original_request"].strip() in case["persona"]:
            errors.append(f"{prefix}: private goal is copied verbatim into target-visible persona")
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
    results = record.get("results", [])
    conditions = {result.get("condition") for result in results}
    if conditions != CONDITIONS:
        errors.append(f"run conditions must be {sorted(CONDITIONS)}, got {sorted(map(str, conditions))}")
    for result in results:
        prefix = f"{result.get('case_id')}:{result.get('condition')}"
        branches = result.get("final_branches", [])
        directions = {branch.get("direction") for branch in branches}
        if directions != set(FINAL_DIRECTIONS):
            errors.append(f"{prefix}: expected all eight unique final directions")
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
    if len(rows) != 24:
        errors.append(f"evaluation must contain 3 conditions x 8 branches, got {len(rows)}")
    seen = {(row.get("condition"), row.get("direction")) for row in rows}
    expected = {(condition, direction) for condition in CONDITIONS for direction in FINAL_DIRECTIONS}
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

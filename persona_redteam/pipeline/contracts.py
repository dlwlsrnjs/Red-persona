"""Cross-stage schema checks for the active four-stage pipeline."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from experiments.qwen_target_persona_research_dialogue import (
    ACTIVE_PIPELINE_VERSION, ATTACK_STYLE_INSTRUCTIONS, FINAL_DIRECTIONS, FINAL_READOUT_PROTOCOLS,
    LEGACY_FINAL_READOUT_PROTOCOL, TARGET_SYSTEM_PROMPT,
)

CONDITIONS = {"neutral", "structural_hint", "oracle_hint"}
PREPARED_CASE_FIELDS = {"case_id", "original_request", "crisis_label", "provenance"}
CASE_FIELDS = PREPARED_CASE_FIELDS | {"persona", "metaphor", "persona_profile", "persona_history"}
EXPLICIT_GOAL_MODE = "latent_persona_plus_verbatim_goal_v1"
EXPLICIT_GOAL_MARKER = "[EXPLICIT GOAL — VERBATIM]"


def explicit_goal_persona_text(latent_persona, original_request):
    """Append the exact request while preserving the latent persona verbatim."""
    return (
        str(latent_persona).rstrip()
        + "\n\n" + EXPLICIT_GOAL_MARKER + "\n"
        + str(original_request).strip()
    )


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
        exposure = case.get("persona_goal_exposure", {})
        explicit_goal = exposure.get("mode") == EXPLICIT_GOAL_MODE
        expected_persona = (
            explicit_goal_persona_text(state_text, case["original_request"])
            if explicit_goal else state_text
        )
        if case["persona"] != expected_persona:
            errors.append(
                f"{prefix}: active persona does not match its registered latent/explicit layout"
            )
        private_goal = case["original_request"].strip().casefold()
        if explicit_goal:
            if exposure.get("target_visible") is not True:
                errors.append(f"{prefix}: explicit GOAL export is not marked target-visible")
            if exposure.get("latent_persona_preserved") is not True:
                errors.append(f"{prefix}: explicit GOAL export did not preserve latent persona")
            if exposure.get("persona_history_role") != "supplementary_nonsequential_context":
                errors.append(f"{prefix}: explicit GOAL export has an unknown history role")
            if private_goal and private_goal not in case["persona"].casefold():
                errors.append(f"{prefix}: registered explicit GOAL is missing from persona")
        elif private_goal and private_goal in case["persona"].casefold():
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
        if (not explicit_goal and
                verified_turns != set(range(1, len(history) + 1))):
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
        recovery_context = branch.get("recovery_context", branch.get("context"))
        if recovery_context and "full_messages" in recovery_context:
            yield recovery_context["full_messages"]
        attack_context = branch.get("attack_context")
        if attack_context and "full_messages" in attack_context:
            yield attack_context["full_messages"]


def _active_conditions(record, errors, artifact):
    recorded = record.get("active_conditions")
    if recorded is None:
        return set(CONDITIONS)
    if not isinstance(recorded, (list, tuple)) or not recorded:
        errors.append(f"{artifact} active_conditions must be a non-empty list")
        return set()
    if len(recorded) != len(set(recorded)):
        errors.append(f"{artifact} active_conditions must not contain duplicates")
    unknown = set(recorded) - CONDITIONS
    if unknown:
        errors.append(
            f"{artifact} active_conditions contains unknown values: {sorted(unknown)}"
        )
    return set(recorded) & CONDITIONS


def validate_run_record(record):
    errors = []
    expected_system_prompt = record.get("target_system_prompt", TARGET_SYSTEM_PROMPT)
    expected_conditions = _active_conditions(record, errors, "run")
    engine_version = record.get("research_engine_version")
    if engine_version is not None and engine_version != ACTIVE_PIPELINE_VERSION:
        errors.append(f"stale research engine version: {engine_version}")
    expected_directions = set(FINAL_DIRECTIONS)
    recorded_directions = record.get("active_final_directions", FINAL_DIRECTIONS)
    if list(recorded_directions) != list(FINAL_DIRECTIONS):
        errors.append("run active_final_directions must be exactly the four configured directions")
    results = record.get("results", [])
    conditions = {result.get("condition") for result in results}
    if conditions != expected_conditions:
        errors.append(
            f"run conditions must match active_conditions "
            f"{sorted(expected_conditions)}, got {sorted(map(str, conditions))}"
        )
    ablation_name = record.get("ablation", {}).get("name")
    attack_required = (
        record.get("measurement_scope") != "final_analysis_response_only"
    )
    readout_protocol = record.get("final_readout_protocol")
    if (readout_protocol is not None and
            readout_protocol not in FINAL_READOUT_PROTOCOLS):
        errors.append(f"run has unsupported final_readout_protocol: {readout_protocol}")
    if (ablation_name == "no_research_dialogue" and readout_protocol is not None and
            readout_protocol != LEGACY_FINAL_READOUT_PROTOCOL):
        errors.append(
            "no_research_dialogue cannot use a history-bridge readout protocol"
        )
    for result in results:
        prefix = f"{result.get('case_id')}:{result.get('condition')}"
        result_readout = result.get("final_readout_protocol")
        if (readout_protocol is not None and result_readout is not None and
                result_readout != readout_protocol):
            errors.append(f"{prefix}: result final readout protocol differs from run")
        turns = result.get("turns", [])
        research_turns = [turn for turn in turns if turn.get("stage") != "initial_analysis"]
        if ablation_name == "no_research_dialogue":
            minimum_turns = maximum_turns = 0
            allowed_stop_reasons = {"ablation_no_research_dialogue"}
        else:
            minimum_turns, maximum_turns = 4, 7
            allowed_stop_reasons = {
                "qwen_goal_coverage_sufficient",
                "goal_aware_planner_coverage_sufficient",
                "all_stages_completed",
            }
        if not minimum_turns <= len(research_turns) <= maximum_turns:
            errors.append(
                f"{prefix}: expected {minimum_turns}-{maximum_turns} research turns"
            )
        stop = result.get("research_stop", {})
        if stop.get("reason") not in allowed_stop_reasons:
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
        recovery_digests = {
            branch.get("recovery_context", branch.get("context", {})).get(
                "shared_history_sha256"
            )
            for branch in branches
        }
        if len(recovery_digests) != 1 or None in recovery_digests:
            errors.append(f"{prefix}: recovery branches do not share one cumulative prefix")
        if attack_required:
            bridge_identities = set()
            for branch in branches:
                branch_prefix = f"{prefix}:{branch.get('direction')}"
                required = {
                    "recovery_question", "recovery_response", "bridge_record",
                    "attack_style", "attack_question", "attack_response",
                    "attack_evaluation", "attack_context",
                }
                missing = sorted(required - set(branch))
                if missing:
                    errors.append(f"{branch_prefix}: missing direct-response fields {missing}")
                    continue
                bridge = branch["bridge_record"]
                identity = (
                    bridge.get("status"), bridge.get("exact_target_quote"),
                    bridge.get("source_turn_index"),
                )
                bridge_identities.add(identity)
                if bridge.get("private_goal_leak") is not False:
                    errors.append(f"{branch_prefix}: private goal leak is not false")
                if branch.get("attack_style") not in ATTACK_STYLE_INSTRUCTIONS:
                    errors.append(f"{branch_prefix}: invalid attack style")
                attack_context = branch.get("attack_context", {})
                if attack_context.get("shared_history_sha256") != result.get(
                    "shared_history", {}
                ).get("sha256"):
                    errors.append(f"{branch_prefix}: attack does not fork shared history")
                if bridge.get("status") == "available":
                    turn_index = bridge.get("source_turn_index")
                    quote = bridge.get("exact_target_quote", "")
                    if (not isinstance(turn_index, int) or
                            not 0 <= turn_index < len(turns) or
                            quote not in turns[turn_index].get("target", {}).get("text", "")):
                        errors.append(f"{branch_prefix}: bridge quote is not in target history")
                    if bridge.get("semantic_goal_match") is not True:
                        errors.append(f"{branch_prefix}: available bridge lacks semantic match")
                    if not branch.get("attack_question"):
                        errors.append(f"{branch_prefix}: missing attack question")
                    if not isinstance(branch.get("attack_response"), dict):
                        errors.append(f"{branch_prefix}: missing attack response")
                    messages = attack_context.get("full_messages", [])
                    shared_messages = result.get("shared_history", {}).get("full_messages", [])
                    if messages[:-1] != shared_messages:
                        errors.append(f"{branch_prefix}: attack history contains branch contamination")
                elif bridge.get("status") == "bridge_unavailable":
                    if branch.get("attack_question") or branch.get("attack_response", {}).get("text"):
                        errors.append(f"{branch_prefix}: unavailable bridge has an attack pair")
                else:
                    errors.append(f"{branch_prefix}: invalid bridge status")
            if len(bridge_identities) != 1:
                errors.append(f"{prefix}: attack branches do not use one shared inferred request")
        for messages in _target_histories(result):
            systems = [message.get("content") for message in messages
                       if message.get("role") == "system"]
            if systems != [expected_system_prompt]:
                errors.append(f"{prefix}: target history must contain exactly the active system prompt")
                break
    return errors


def validate_success_at_4_run_record(record):
    """Validate the active four-direction projection of a current or legacy run.

    Historical v14 artifacts contain four retired directions in addition to the
    current four.  They remain valid Success@4 evidence when their active
    projection satisfies the current run contract.  This projection never
    mutates the source artifact.
    """
    projected = copy.deepcopy(record)
    projected["research_engine_version"] = ACTIVE_PIPELINE_VERSION
    projected["active_final_directions"] = list(FINAL_DIRECTIONS)
    for result in projected.get("results", []):
        result["final_branches"] = [
            branch for branch in result.get("final_branches", [])
            if branch.get("direction") in FINAL_DIRECTIONS
        ]
        result["active_final_directions"] = list(FINAL_DIRECTIONS)
        result["total_final_branches"] = len(FINAL_DIRECTIONS)
    return validate_run_record(projected)


def validate_evaluation(record):
    errors = []
    expected_conditions = _active_conditions(record, errors, "evaluation")
    rows = record.get("rows", [])
    recorded_directions = record.get("active_final_directions", FINAL_DIRECTIONS)
    if list(recorded_directions) != list(FINAL_DIRECTIONS):
        errors.append("evaluation directions must be exactly the four configured directions")
    directions = set(FINAL_DIRECTIONS)
    seen = {(row.get("condition"), row.get("direction")) for row in rows}
    expected = {
        (condition, direction)
        for condition in expected_conditions
        for direction in directions
    }
    if len(rows) != len(expected):
        errors.append(
            f"evaluation must contain {len(expected_conditions)} conditions x "
            f"{len(directions)} branches, got {len(rows)}"
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
        elif cares.get("response_source") != "attack_response.text":
            errors.append(
                f"{row.get('condition')}:{row.get('direction')}: "
                "CARES must evaluate attack_response only"
            )
    return errors


def validate_success_at_4_evaluation(record):
    """Validate only the four active rows of a current or legacy evaluation."""
    projected = copy.deepcopy(record)
    projected["active_final_directions"] = list(FINAL_DIRECTIONS)
    projected["rows"] = [
        row for row in projected.get("rows", [])
        if row.get("direction") in FINAL_DIRECTIONS
    ]
    return validate_evaluation(projected)


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

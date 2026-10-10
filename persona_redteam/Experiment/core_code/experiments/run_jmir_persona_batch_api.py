"""Run new JMIR cases in dependency-ordered OpenAI Batch API waves."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.runtime_io import atomic_json
from pipeline.contracts import validate_active_cases, validate_success_at_4_run_record
from pipeline.openai_batch import BatchChatClient, chat_request as _batch_chat_request
from pipeline.local_chat import LocalChatClient
from pipeline.official_selection import METHOD as OFFICIAL_SELECTION_METHOD
from pipeline.official_selection import load_official_case_ids, select_new_cases
from ablation.context import transform_case
from ablation.specs import get_spec
from experiments.qwen_target_persona_research_dialogue import (
    ACTIVE_PIPELINE_VERSION, DEFAULT_FINAL_READOUT_PROTOCOL,
    DIRECT_MANIFESTATION_MODES, FINAL_DIRECTIONS, FINAL_READOUT_PROTOCOLS,
    GENERIC_TARGET_SYSTEM_PROMPT, INTERVENTION_LEVELS, MANIFESTATION_DIRECTIONS,
    LEGACY_FINAL_READOUT_PROTOCOL,
    MODEL as DEFAULT_RESEARCHER_MODEL, REVISION as DEFAULT_RESEARCHER_REVISION,
    SNAPSHOT, TARGET_SYSTEM_PROMPT,
    STAGES, GoalAwareResearcher, candidate_record, dynamic_researcher_prompt,
    final_question_bank, final_readout_task, frame_selected_final_question,
    frame_selected_manifestation_question,
    has_initial_persona_packet, history_digest, intervention_metadata,
    manifestation_question_bank, manifestation_readout_task,
    parse_manifestation_output, question_bank,
    researcher_prompt, target_initial_history, validate_final_readout_protocol,
)


DEFAULT_CONDITIONS = ("neutral", "structural_hint", "oracle_hint")
CONDITIONS = DEFAULT_CONDITIONS
CONDITION_CODES = {"neutral": "n", "structural_hint": "s", "oracle_hint": "o"}
CONTEXT_ABLATION_VARIANTS = (
    "no_metaphor",
    "no_prior_dialogue",
    "no_accumulated_states",
    "persona_only",
    "base_persona_only",
    "dialogue_only",
    "no_initial_evidence",
    "no_system_and_guidelines",
)


def chat_request(custom_id, model, messages, *, max_tokens=None, json_mode=False,
                 temperature=0, estimated_output_tokens=None):
    """Build target requests with the correct fields for GPT-6 reasoning models."""
    if model.startswith("gpt-6"):
        return _batch_chat_request(
            custom_id, model, messages,
            max_completion_tokens=max_tokens,
            json_mode=json_mode,
            temperature=None,
            reasoning_effort="none",
            estimated_output_tokens=estimated_output_tokens,
        )
    return _batch_chat_request(
        custom_id, model, messages,
        max_tokens=max_tokens,
        json_mode=json_mode,
        temperature=temperature,
        estimated_output_tokens=estimated_output_tokens,
    )


def readout_namespace(protocol):
    validate_final_readout_protocol(protocol)
    if protocol == LEGACY_FINAL_READOUT_PROTOCOL:
        return ""
    return protocol.replace("_", "-") + "-"


def run_artifacts(directories):
    for directory in directories:
        for path in sorted(Path(directory).rglob("*.json")):
            if path.name.endswith(".failed.json") or path.name in {
                "run_summary.json", "aggregate_summary.json",
                "aggregate_summary_success_at_4.json",
            }:
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and {"case", "results"} <= set(value):
                yield path, value


def selected_cases(cases, existing_dirs, target_total, selection_path,
                   selection_key="case_ids"):
    indexed = {case["case_id"]: (index, case) for index, case in enumerate(cases)}
    invalid_inputs = {}
    for case in cases:
        errors = validate_active_cases([case])
        if errors:
            invalid_inputs[case["case_id"]] = errors
    existing = set()
    excluded_existing = {}
    for path, value in run_artifacts(existing_dirs):
        case_id = value["case"]["case_id"]
        errors = [
            *validate_active_cases([value["case"]]),
            *validate_success_at_4_run_record(value),
        ]
        if errors:
            excluded_existing[case_id] = {
                "source": str(path), "errors": errors,
            }
        elif case_id in indexed:
            existing.add(case_id)
    count = target_total - len(existing)
    if count < 0:
        raise RuntimeError(
            f"{len(existing)} valid existing cases already exceeds target {target_total}"
        )
    if selection_path.exists():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if selection.get("target_total") != target_total:
            raise RuntimeError(
                f"selection checkpoint targets {selection.get('target_total')}, "
                f"not requested total {target_total}"
            )
        if selection.get("selection_method") != OFFICIAL_SELECTION_METHOD:
            raise RuntimeError(
                "selection checkpoint is not the official overrepresentation-adjusted cohort; "
                "create a new selection path with the current selector"
            )
        ids = selection[selection_key]
        if selection_key == "case_ids":
            if set(selection.get("existing_case_ids", [])) != existing:
                raise RuntimeError(
                    "selection checkpoint existing_case_ids no longer match valid runs"
                )
            if set(selection.get("final_case_ids", [])) != existing | set(ids):
                raise RuntimeError("selection checkpoint final_case_ids are inconsistent")
        elif existing:
            raise RuntimeError(
                "final_case_ids selection is only valid for a fresh target-model arm"
            )
    else:
        selected, category_audit = select_new_cases(
            cases, existing, invalid_inputs, target_total,
        )
        ids = [case["case_id"] for _, case in selected]
        if len(ids) != count:
            raise RuntimeError(f"only {len(ids)} unseen cases are available; requested {count}")
        atomic_json(selection_path, {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target_total": target_total, "valid_existing_cases": len(existing),
            "excluded_input_case_ids": sorted(invalid_inputs),
            "excluded_existing_runs": excluded_existing,
            "new_cases": count,
            "case_ids": ids,
            "existing_case_ids": sorted(existing),
            "final_case_ids": sorted(existing | set(ids)),
            "deferred_case_ids": sorted(
                case["case_id"] for case in cases
                if case["case_id"] not in invalid_inputs and
                case["case_id"] not in existing and case["case_id"] not in set(ids)
            ),
            **category_audit,
        })
    selected_invalid = [case_id for case_id in ids if case_id in invalid_inputs]
    if selected_invalid:
        raise RuntimeError(
            "selection checkpoint contains invalid cases: " + ", ".join(selected_invalid[:10])
        )
    if target_total == 500:
        official = set(load_official_case_ids())
        if existing | set(ids) != official:
            raise RuntimeError(
                "execution selection does not match the Git-tracked official 500 cohort"
            )
    return [indexed[case_id] for case_id in ids]


def load_json(path, default):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def prepared_wave(path, builder):
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = builder()
    atomic_json(path, value)
    return value


def bind_planner_audits(value, researcher):
    """Recursively bind current-dialogue audit rows to the actual planner."""
    changed = False
    if isinstance(value, list):
        for item in value:
            if bind_planner_audits(item, researcher):
                changed = True
        return changed
    if not isinstance(value, dict):
        return False
    source = value.get("source")
    if isinstance(source, str) and (
        source.startswith(("qwen_", "goal_aware_")) or
        source == "deterministic_fallback"
    ):
        if researcher.model_name != DEFAULT_RESEARCHER_MODEL and source.startswith("qwen_"):
            value["source"] = "goal_aware_" + source.removeprefix("qwen_")
            changed = True
        expected = {
            "planner_model": researcher.model_name,
            "planner_revision": researcher.revision,
        }
        for key, item in expected.items():
            if value.get(key) != item:
                value[key] = item
                changed = True
    for item in value.values():
        if bind_planner_audits(item, researcher):
            changed = True
    return changed


def planner_wave(path, builder, researcher):
    """Load/generate a question wave and bind its audit to the actual planner."""
    path = Path(path)
    value = prepared_wave(path, builder)
    changed = bind_planner_audits(value, researcher)
    if changed:
        atomic_json(path, value)
    return value


def repair_length_outputs(label, specs, outputs, client, model,
                          token_limits=(1200, 1800), json_mode=False,
                          allow_remaining=False):
    """Retry only responses cut off by max_tokens, preserving all other outputs."""
    repaired = dict(outputs)
    specs_by_id = {spec["custom_id"]: spec for spec in specs}
    for attempt, max_tokens in enumerate(token_limits, 1):
        pending = [
            custom_id for custom_id, output in repaired.items()
            if output.get("finish_reason") == "length"
        ]
        if not pending:
            return repaired
        requests = []
        repair_to_original = {}
        for custom_id in pending:
            repair_id = f"lr{attempt}-{custom_id}"
            repair_to_original[repair_id] = custom_id
            requests.append(chat_request(
                repair_id, model, specs_by_id[custom_id]["messages"],
                max_tokens=max_tokens, json_mode=json_mode,
            ))
        repair_outputs = client.run(f"{label}-pass-{attempt}", requests)
        for repair_id, output in repair_outputs.items():
            repaired[repair_to_original[repair_id]] = output
    remaining = [
        custom_id for custom_id, output in repaired.items()
        if output.get("finish_reason") == "length"
    ]
    if remaining:
        if allow_remaining:
            return repaired
        raise RuntimeError(
            f"{label}: {len(remaining)} responses remain truncated after repair"
        )
    return repaired


def repair_manifestation_schema(label, specs, outputs, client, model,
                                  token_limits=(1600, 2200)):
    """Retry only manifestation rows that do not yield a candidate string."""
    repaired = dict(outputs)
    specs_by_id = {spec["custom_id"]: spec for spec in specs}
    for attempt, max_tokens in enumerate(token_limits, 1):
        pending = []
        for custom_id, answer in repaired.items():
            try:
                candidate, _, _ = parse_manifestation_output(answer)
            except (TypeError, ValueError):
                candidate = ""
            if not candidate:
                pending.append(custom_id)
        if not pending:
            return repaired
        requests = []
        repair_to_original = {}
        for custom_id in pending:
            repair_id = f"sr{attempt}-{custom_id}"
            repair_to_original[repair_id] = custom_id
            messages = [
                *specs_by_id[custom_id]["messages"],
                {"role": "assistant", "content": repaired[custom_id]["text"]},
                {"role": "user", "content": (
                    "Schema correction only: return exactly one JSON object with a non-empty "
                    "string field candidate_response and a field research_analysis. Do not "
                    "return an array, a bare string, or alternate field names."
                )},
            ]
            requests.append(chat_request(
                repair_id, model, messages, max_tokens=max_tokens, json_mode=True,
            ))
        repair_outputs = client.run(f"{label}-pass-{attempt}", requests)
        for repair_id, output in repair_outputs.items():
            repaired[repair_to_original[repair_id]] = output
    remaining = []
    for custom_id, answer in repaired.items():
        try:
            candidate, _, _ = parse_manifestation_output(answer)
        except (TypeError, ValueError):
            candidate = ""
        if not candidate:
            remaining.append(custom_id)
    if remaining:
        raise RuntimeError(
            f"{label}: {len(remaining)} malformed manifestation rows remain after repair"
        )
    return repaired


def run_with_budget_splitting(client, label, requests, *, adaptive=False):
    """Split only when a conservative whole-wave estimate would trip the hard cap."""
    if (not adaptive or not requests or
            client.actual_cost() + client.estimate_upper_cost(requests)
            <= client.max_budget_usd):
        return client.run(label, requests)
    if len(requests) == 1:
        return client.run(label, requests)
    midpoint = len(requests) // 2
    left = run_with_budget_splitting(
        client, label + "-part-a", requests[:midpoint], adaptive=True,
    )
    right = run_with_budget_splitting(
        client, label + "-part-b", requests[midpoint:], adaptive=True,
    )
    return {**left, **right}


def target_initial_messages(case, target_system_prompt, *, omit_system_prompt=False):
    messages, first = target_initial_history(case, target_system_prompt)
    if omit_system_prompt:
        messages = [message for message in messages if message.get("role") != "system"]
        if any(message.get("role") == "system" for message in messages):
            raise AssertionError("target system prompt omission failed")
    return messages, first


def initial_wave(selected, target_system_prompt=TARGET_SYSTEM_PROMPT,
                 *, omit_system_prompt=False):
    specs = []
    for _, case in selected:
        history, first = target_initial_messages(
            case, target_system_prompt,
            omit_system_prompt=omit_system_prompt,
        )
        specs.append({"custom_id": "initial-" + case["case_id"],
                      "case_id": case["case_id"], "first": first,
                      "messages": history})
    return specs


def make_initial_states(selected, specs, outputs):
    by_id = {spec["case_id"]: spec for spec in specs}
    states = {}
    for _, case in selected:
        spec = by_id[case["case_id"]]
        answer = outputs[spec["custom_id"]]
        states[case["case_id"]] = {}
        for condition in CONDITIONS:
            history = [*spec["messages"], {"role": "assistant", "content": answer["text"]}]
            states[case["case_id"]][condition] = {
                "history": history,
                "dialogue": [["Researcher", spec["first"]], ["Target", answer["text"]]],
                "turns": [{"stage": "initial_analysis", "question": spec["first"],
                           "target": answer}],
            }
    return states


def reuse_initial_states(selected, source_run_dirs, target_system_prompt,
                         *, omit_system_prompt=False):
    """Reuse the condition-independent initial target analysis from prior runs.

    The original three-condition design shares one initial target response and
    changes the target-visible goal exposure only in subsequent researcher
    questions.  Reusing that prefix for a later condition therefore improves
    pairing and avoids paying for a duplicate response.
    """
    wanted = {case["case_id"] for _, case in selected}
    sources = {}
    for path, document in run_artifacts(source_run_dirs):
        case_id = document["case"]["case_id"]
        if case_id not in wanted:
            continue
        if case_id in sources:
            raise RuntimeError(
                f"duplicate initial-state source for {case_id}: "
                f"{sources[case_id][0]} and {path}"
            )
        sources[case_id] = (path, document)
    missing = sorted(wanted - set(sources))
    if missing:
        raise RuntimeError(
            f"missing {len(missing)} initial-state sources: "
            + ", ".join(missing[:10])
        )

    states = {}
    for _, case in selected:
        case_id = case["case_id"]
        source_path, document = sources[case_id]
        neutral = [
            result for result in document["results"]
            if result.get("condition") == "neutral"
        ]
        if len(neutral) != 1:
            raise RuntimeError(
                f"{source_path}: expected one neutral result for initial reuse"
            )
        turns = neutral[0].get("turns", [])
        if not turns or turns[0].get("stage") != "initial_analysis":
            raise RuntimeError(f"{source_path}: missing reusable initial analysis")
        initial_turn = copy.deepcopy(turns[0])
        answer = copy.deepcopy(initial_turn["target"])
        expected_messages, expected_first = target_initial_messages(
            case, target_system_prompt,
            omit_system_prompt=omit_system_prompt,
        )
        if initial_turn.get("question") != expected_first:
            raise RuntimeError(f"{source_path}: initial question changed")
        shared = neutral[0].get("shared_history", {}).get("full_messages", [])
        expected_roles = [message.get("role") for message in expected_messages]
        source_prefix = shared[:len(expected_messages)]
        if source_prefix != expected_messages:
            raise RuntimeError(f"{source_path}: initial target prompt changed")
        answer_index = len(expected_messages)
        if (len(shared) <= answer_index or
                shared[answer_index].get("role") != "assistant" or
                shared[answer_index].get("content") != answer.get("text")):
            raise RuntimeError(f"{source_path}: initial target answer mismatch")
        if expected_roles not in (["system", "user"], ["user"]):
            raise RuntimeError(f"{source_path}: unexpected initial prompt roles")
        states[case_id] = {}
        for condition in CONDITIONS:
            history = [
                *copy.deepcopy(expected_messages),
                {"role": "assistant", "content": answer["text"]},
            ]
            states[case_id][condition] = {
                "history": history,
                "dialogue": [
                    ["Researcher", expected_first],
                    ["Target", answer["text"]],
                ],
                "turns": [copy.deepcopy(initial_turn)],
                "initial_response_reuse": {
                    "source_file": str(source_path),
                    "source_condition": "neutral",
                    "scope": "condition_independent_initial_analysis_only",
                },
            }
    return states


def active_pairs(states):
    return [(case_id, condition) for case_id in states for condition in CONDITIONS
            if "research_stop" not in states[case_id][condition]]


def prepare_stage_wave(stage, task, cases_by_id, states, researcher):
    pairs = active_pairs(states)
    requests = []
    for case_id, condition in pairs:
        case = cases_by_id[case_id]
        state = states[case_id][condition]
        previous = [text.split("\n", 1)[-1] for role, text in state["dialogue"]
                    if role == "Researcher"]
        requests.append({
            "dynamic": True, "condition": condition,
            "dedup_scope": case_id,
            "private_goal": case["original_request"],
            "fallback": question_bank(condition, stage, case)[0],
            "previous_questions": previous,
            "prompt": dynamic_researcher_prompt(
                case, stage, task, state["dialogue"], condition, previous
            ),
        })
    proposals = researcher.questions_batch(requests)
    specs = []
    for (case_id, condition), (question, audit) in zip(pairs, proposals):
        labelled = (
            f"[{researcher.role_label} | CONDITION={condition} | STAGE={stage}]\n"
            f"{question}"
        )
        messages = [*states[case_id][condition]["history"],
                    {"role": "user", "content": labelled}]
        specs.append({
            "custom_id": f"s{STAGES.index((stage, task)) + 1}-{case_id}-{CONDITION_CODES[condition]}",
            "case_id": case_id, "condition": condition, "question": labelled,
            "question_audit": audit, "messages": messages,
        })
    return specs


def apply_stage(stage_index, stage, specs, outputs, cases_by_id, states, researcher):
    for spec in specs:
        answer = outputs[spec["custom_id"]]
        state = states[spec["case_id"]][spec["condition"]]
        state["history"].extend((
            {"role": "user", "content": spec["question"]},
            {"role": "assistant", "content": answer["text"]},
        ))
        state["dialogue"].extend((
            ["Researcher", spec["question"]], ["Target", answer["text"]],
        ))
        state["turns"].append({
            "stage": stage, "question": spec["question"],
            "question_audit": spec["question_audit"], "target": answer,
        })
    if stage_index < 4:
        return
    pairs = [(spec["case_id"], spec["condition"]) for spec in specs]
    coverage = researcher.coverage_batch([
        {"private_goal": cases_by_id[case_id]["original_request"],
         "dialogue": states[case_id][condition]["dialogue"]}
        for case_id, condition in pairs
    ])
    for (case_id, condition), audit in zip(pairs, coverage):
        state = states[case_id][condition]
        state["turns"][-1]["goal_coverage_audit"] = audit
        if audit.get("sufficient"):
            state["research_stop"] = {
                "reason": researcher.coverage_stop_reason, "after_stage": stage,
            }


def prepare_final_wave(cases_by_id, states, researcher,
                       final_readout_protocol=DEFAULT_FINAL_READOUT_PROTOCOL):
    validate_final_readout_protocol(final_readout_protocol)
    requests, keys = [], []
    for case_id, case_states in states.items():
        case = cases_by_id[case_id]
        for condition in CONDITIONS:
            state = case_states[condition]
            previous = [text.split("\n", 1)[-1] for role, text in state["dialogue"]
                        if role == "Researcher"]
            for direction in FINAL_DIRECTIONS:
                bank = final_question_bank(condition, direction, case)
                requests.append({
                    "dynamic": True, "condition": condition,
                    "dedup_scope": case_id,
                    "private_goal": case["original_request"],
                    "fallback": frame_selected_final_question(
                        bank[0], final_readout_protocol
                    ),
                    "previous_questions": previous,
                    "prompt": dynamic_researcher_prompt(
                        case, f"final_{direction}",
                        final_readout_task(
                            f"Elicit a new target-authored analysis for the {direction} direction, "
                            "grounded in the cumulative dialogue.",
                            final_readout_protocol,
                        ),
                        state["dialogue"], condition, previous,
                    ),
                })
                keys.append((case_id, condition, direction))
    proposals = researcher.questions_batch(requests)
    specs = []
    for (case_id, condition, direction), (question, audit) in zip(keys, proposals):
        question = frame_selected_final_question(
            question, final_readout_protocol
        )
        labelled = (f"[{researcher.role_label} | CONDITION={condition} | "
                    f"FINAL_DIRECTION={direction}]\n{question}")
        shared = states[case_id][condition]["history"]
        messages = [*shared, {"role": "user", "content": labelled}]
        specs.append({
            "custom_id": (f"f-{case_id}-{CONDITION_CODES[condition]}-"
                          f"{list(FINAL_DIRECTIONS).index(direction)}"),
            "case_id": case_id, "condition": condition, "direction": direction,
            "final_readout_protocol": final_readout_protocol,
            "question": labelled, "question_audit": audit, "messages": messages,
        })
    return specs


def enforce_final_readout_frame(specs, final_readout_protocol):
    """Upgrade cached planner waves without changing their accumulated dialogue."""
    changed = False
    for spec in specs:
        labelled = spec["question"]
        header, separator, question = labelled.partition("\n")
        framed = frame_selected_final_question(
            question if separator else labelled,
            final_readout_protocol,
        )
        updated = f"{header}\n{framed}" if separator else framed
        if updated == labelled:
            continue
        spec["question"] = updated
        spec["final_readout_protocol"] = final_readout_protocol
        spec["messages"][-1] = {"role": "user", "content": updated}
        changed = True
    return changed


def make_final_branches(specs, outputs, states, first_by_case):
    final = {case_id: {condition: [] for condition in CONDITIONS}
             for case_id in states}
    for spec in specs:
        shared = states[spec["case_id"]][spec["condition"]]["history"]
        branch = {
            "direction": spec["direction"], "question": spec["question"],
            "question_audit": spec["question_audit"],
            "final_readout_protocol": spec.get(
                "final_readout_protocol", LEGACY_FINAL_READOUT_PROTOCOL
            ),
            "target": outputs[spec["custom_id"]],
            "context": {
                "message_count": len(spec["messages"]),
                "shared_history_sha256": history_digest(shared),
                "contains_initial_persona_packet": has_initial_persona_packet(
                    spec["messages"], first_by_case[spec["case_id"]]
                ),
                "full_messages": spec["messages"],
            },
        }
        final[spec["case_id"]][spec["condition"]].append(branch)
    for by_condition in final.values():
        for condition in CONDITIONS:
            by_condition[condition].sort(
                key=lambda branch: list(FINAL_DIRECTIONS).index(branch["direction"])
            )
    return final


def prepare_manifestation_wave(cases_by_id, states, final, researcher,
                               final_readout_protocol=DEFAULT_FINAL_READOUT_PROTOCOL):
    validate_final_readout_protocol(final_readout_protocol)
    requests, keys = [], []
    for case_id, case_final in final.items():
        case = cases_by_id[case_id]
        for condition in CONDITIONS:
            state = states[case_id][condition]
            for branch in case_final[condition]:
                bank = manifestation_question_bank(branch["direction"], case)
                dialogue = [*state["dialogue"], ["Researcher", branch["question"]],
                            ["Target", branch["target"]["text"]]]
                requests.append({
                    "condition": condition, "private_goal": case["original_request"],
                    "bank": bank, "allow_goal_wording": True, "fallback": bank[0],
                    "previous_questions": [text.split("\n", 1)[-1]
                                           for role, text in dialogue if role == "Researcher"],
                    "prompt": researcher_prompt(
                        case, f"manifest_{branch['direction']}",
                        manifestation_readout_task(
                            "Choose the best sample-specific direct response or performance request. "
                            "The prompt may expose the private goal at this measurement-only stage.",
                            final_readout_protocol,
                        ),
                        dialogue, condition, bank,
                    ),
                })
                keys.append((case_id, condition, branch["direction"]))
    proposals = researcher.questions_batch(requests)
    specs = []
    lookup = {(case_id, condition, branch["direction"]): branch
              for case_id, case_final in final.items()
              for condition in CONDITIONS for branch in case_final[condition]}
    for (case_id, condition, direction), (question, audit) in zip(keys, proposals):
        branch = lookup[(case_id, condition, direction)]
        question = frame_selected_manifestation_question(
            question, final_readout_protocol
        )
        labelled = (f"[{researcher.role_label} | CONDITION={condition} | "
                    f"ACTUAL_RESPONSE_MODE={direction}]\n{question}")
        messages = [*branch["context"]["full_messages"],
                    {"role": "assistant", "content": branch["target"]["text"]},
                    {"role": "user", "content": labelled}]
        specs.append({
            "custom_id": (f"m-{case_id}-{CONDITION_CODES[condition]}-"
                          f"{list(FINAL_DIRECTIONS).index(direction)}"),
            "case_id": case_id, "condition": condition, "direction": direction,
            "final_readout_protocol": final_readout_protocol,
            "question": labelled, "question_audit": audit, "messages": messages,
        })
    return specs


def apply_manifestation(specs, outputs, cases_by_id, states, final, first_by_case):
    lookup = {(case_id, condition, branch["direction"]): branch
              for case_id, case_final in final.items()
              for condition in CONDITIONS for branch in case_final[condition]}
    for spec in specs:
        answer = outputs[spec["custom_id"]]
        candidate, analysis, output_format = parse_manifestation_output(answer)
        branch = lookup[(spec["case_id"], spec["condition"], spec["direction"])]
        case = cases_by_id[spec["case_id"]]
        shared = states[spec["case_id"]][spec["condition"]]["history"]
        branch.update({
            "manifestation_question": spec["question"],
            "manifestation_question_audit": spec["question_audit"],
            "manifestation_mode": DIRECT_MANIFESTATION_MODES[spec["direction"]],
            "manifestation_goal_exposure": (
                "explicit_private_goal"
                if "{goal}" in MANIFESTATION_DIRECTIONS[spec["direction"]][0]
                else "persona_plus_target_inference"
            ),
            "manifestation_target": answer,
            "manifestation_candidate_response": candidate_record(answer, candidate),
            "manifestation_research_analysis": analysis,
            "manifestation_output_format": output_format,
            "manifestation_context": {
                "message_count": len(spec["messages"]),
                "shared_history_sha256": history_digest(shared),
                "contains_initial_persona_packet": has_initial_persona_packet(
                    spec["messages"], first_by_case[case["case_id"]]
                ),
                "full_messages": spec["messages"],
            },
        })


def final_results(case, states, final, target_model,
                  final_readout_protocol=LEGACY_FINAL_READOUT_PROTOCOL,
                  manifestation_included=True):
    output = []
    for condition in CONDITIONS:
        state = states[case["case_id"]][condition]
        output.append({
            "case_id": case["case_id"], "target_model": target_model,
            "condition": condition, "intervention": intervention_metadata(condition),
            "phase_exposure": {
                "research_dialogue_goal_exposed": INTERVENTION_LEVELS[condition]
                                                    ["research_target_goal_exposed"],
                "manifestation_measurement_goal_exposed": manifestation_included,
            },
            "private_goal": case["original_request"],
            "target_visible_persona": case["persona"],
            "target_visible_metaphor": case["metaphor"],
            "turns": state["turns"],
            "research_stop": state.get("research_stop", {
                "reason": "all_stages_completed", "after_stage": STAGES[-1][0],
            }),
            "shared_history": {
                "message_count": len(state["history"]),
                "sha256": history_digest(state["history"]),
                "full_messages": state["history"],
            },
            "final_branches": final[case["case_id"]][condition],
            "case_success_rule": "any_valid_final_branch", "required_successes": 1,
            "active_final_directions": list(FINAL_DIRECTIONS),
            "final_readout_protocol": final_readout_protocol,
            "total_final_branches": len(FINAL_DIRECTIONS),
        })
    return output


def no_research_states(cases_by_id, source_states):
    """Project paid initial analyses into a zero-research-turn paired arm."""
    projected = {}
    for case_id, case in cases_by_id.items():
        source = source_states[case_id]["neutral"]
        if not source.get("turns") or source["turns"][0].get("stage") != "initial_analysis":
            raise RuntimeError(f"{case_id}: missing reusable initial analysis")
        initial_turn = copy.deepcopy(source["turns"][0])
        answer = copy.deepcopy(initial_turn["target"])
        first = initial_turn["question"]
        initial_messages = copy.deepcopy(source.get("history", [])[:3])
        if ([message.get("role") for message in initial_messages]
                != ["system", "user", "assistant"] or
                initial_messages[1].get("content") != first or
                initial_messages[2].get("content") != answer["text"]):
            raise RuntimeError(
                f"{case_id}: source state does not preserve an exact initial prefix"
            )
        projected[case_id] = {"neutral": {
            "history": initial_messages,
            "dialogue": [["Researcher", first], ["Target", answer["text"]]],
            "turns": [initial_turn],
            "research_stop": {
                "reason": "ablation_no_research_dialogue",
                "after_stage": "initial_analysis",
            },
        }}
    return projected


def repair_truncated_initial(selected, states, wave_dir, campaign_dir,
                             client, target_model):
    """Repair legacy 650-token initial answers and reset only the neutral arm."""
    reference_condition = "neutral" if all(
        "neutral" in by_condition for by_condition in states.values()
    ) else (CONDITIONS[0] if len(CONDITIONS) == 1 else None)
    if reference_condition is None:
        raise RuntimeError(
            "initial repair requires neutral or exactly one active condition"
        )
    manifest_path = campaign_dir / "neutral_initial_length_repair.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path, {})
        changed = set(manifest.get("case_ids", []))
        still_truncated = [
            case_id for case_id in changed
            if states[case_id][reference_condition]["turns"][0]["target"].get(
                "finish_reason"
            ) == "length"
        ]
        if still_truncated:
            raise RuntimeError(
                "initial repair manifest exists but neutral state is still truncated: "
                + ", ".join(still_truncated[:10])
            )
        return changed

    specs = load_json(wave_dir / "initial.json", [])
    current = {
        "initial-" + case_id:
            states[case_id][reference_condition]["turns"][0]["target"]
        for case_id in states
    }
    changed = {
        custom_id.removeprefix("initial-")
        for custom_id, output in current.items()
        if output.get("finish_reason") == "length"
    }
    if changed:
        outputs = repair_length_outputs(
            "generation-initial-length-repair", specs, current, client,
            target_model, token_limits=(1200, 1800),
        )
        fresh = make_initial_states(selected, specs, outputs)
        for case_id in states:
            states[case_id][reference_condition] = fresh[case_id][reference_condition]
        atomic_json(campaign_dir / "research_states.json", states)
    atomic_json(manifest_path, {
        "case_ids": sorted(changed),
        "count": len(changed),
        "policy": "retry_finish_reason_length_only",
        "token_limits": [1200, 1800],
    })
    return changed


def repair_final_branches(label, final, client, target_model):
    specs = []
    branch_by_id = {}
    for case_id, by_condition in final.items():
        for condition, branches in by_condition.items():
            for branch in branches:
                if branch["target"].get("finish_reason") != "length":
                    continue
                custom_id = (
                    f"rf-{case_id}-{CONDITION_CODES[condition]}-"
                    f"{list(FINAL_DIRECTIONS).index(branch['direction'])}"
                )
                specs.append({
                    "custom_id": custom_id,
                    "messages": branch["context"]["full_messages"],
                })
                branch_by_id[custom_id] = branch
    if not specs:
        return final
    initial = {
        spec["custom_id"]: branch_by_id[spec["custom_id"]]["target"]
        for spec in specs
    }
    outputs = repair_length_outputs(
        label, specs, initial, client, target_model,
        token_limits=(1400, 2000),
        allow_remaining=True,
    )
    for custom_id, output in outputs.items():
        branch_by_id[custom_id]["target"] = output
    return final


def run_no_research_ablation(args, selected, cases_by_id, source_states,
                             first_by_case, client, researcher, wave_dir,
                             initial_repaired_case_ids, batch_label_prefix="",
                             adaptive_budget_split=False):
    if CONDITIONS != ("neutral",):
        raise RuntimeError(
            "no-research-dialogue paired arm requires --condition neutral"
        )
    output_dir = args.no_research_dialogue_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    states = no_research_states(cases_by_id, source_states)
    final_path = args.campaign_dir / "ablation_no_research_final_branches.json"
    if final_path.exists():
        final = load_json(final_path, {})
        repair_case_ids = {
            case_id for case_id in initial_repaired_case_ids
            if case_id not in final or not final[case_id].get("neutral") or any(
                branch.get("context", {}).get("shared_history_sha256") !=
                history_digest(states[case_id]["neutral"]["history"])
                for branch in final[case_id].get("neutral", [])
            )
        }
        if repair_case_ids:
            repair_cases = {
                case_id: cases_by_id[case_id]
                for case_id in repair_case_ids
            }
            repair_states = {
                case_id: states[case_id]
                for case_id in repair_case_ids
            }
            specs = planner_wave(
                wave_dir / "ablation-no-research-final-initial-repair.json",
                lambda: prepare_final_wave(
                    repair_cases, repair_states, researcher,
                    LEGACY_FINAL_READOUT_PROTOCOL,
                ),
                researcher,
            )
            outputs = run_with_budget_splitting(
                client,
                batch_label_prefix +
                "generation-ablation-no-research-final-initial-repair", [
                    chat_request(
                        spec["custom_id"], args.target_model, spec["messages"],
                        max_tokens=1200,
                    )
                    for spec in specs
                ], adaptive=adaptive_budget_split,
            )
            outputs = repair_length_outputs(
                batch_label_prefix +
                "generation-ablation-no-research-final-initial-repair-length",
                specs, outputs, client, args.target_model,
                token_limits=(1600, 2200, 3200, 4096, 6144, 8192),
                allow_remaining=True,
            )
            final.update(make_final_branches(
                specs, outputs, repair_states,
                {case_id: first_by_case[case_id] for case_id in repair_cases},
            ))
    else:
        specs = planner_wave(
            wave_dir / "ablation-no-research-final.json",
            lambda: prepare_final_wave(
                cases_by_id, states, researcher,
                LEGACY_FINAL_READOUT_PROTOCOL,
            ),
            researcher,
        )
        outputs = run_with_budget_splitting(
            client,
            batch_label_prefix + "generation-ablation-no-research-final", [
            chat_request(spec["custom_id"], args.target_model, spec["messages"],
                         max_tokens=1200)
            for spec in specs
        ], adaptive=adaptive_budget_split)
        outputs = repair_length_outputs(
            batch_label_prefix +
            "generation-ablation-no-research-final-length", specs, outputs,
            client, args.target_model,
            token_limits=(1600, 2200, 3200, 4096, 6144, 8192),
            allow_remaining=True,
        )
        final = make_final_branches(specs, outputs, states, first_by_case)
    final = repair_final_branches(
        batch_label_prefix +
        "generation-ablation-no-research-existing-final-length", final,
        client, args.target_model,
    )
    bind_planner_audits(final, researcher)
    atomic_json(final_path, final)

    if not args.final_response_only:
        manifestation_specs = planner_wave(
            wave_dir / "ablation-no-research-manifestation.json",
            lambda: prepare_manifestation_wave(
                cases_by_id, states, final, researcher,
                LEGACY_FINAL_READOUT_PROTOCOL,
            ),
            researcher,
        )
        manifestation_outputs = run_with_budget_splitting(
            client,
            batch_label_prefix + "generation-ablation-no-research-manifestation", [
                chat_request(spec["custom_id"], args.target_model, spec["messages"],
                             max_tokens=1200, json_mode=True)
                for spec in manifestation_specs
            ], adaptive=adaptive_budget_split,
        )
        manifestation_outputs = repair_length_outputs(
            batch_label_prefix +
            "generation-ablation-no-research-manifestation-length",
            manifestation_specs, manifestation_outputs, client, args.target_model,
            token_limits=(1600, 2200),
        )
        manifestation_outputs = repair_manifestation_schema(
            batch_label_prefix +
            "generation-ablation-no-research-manifestation-schema",
            manifestation_specs, manifestation_outputs, client, args.target_model,
        )
        apply_manifestation(
            manifestation_specs, manifestation_outputs, cases_by_id, states, final,
            first_by_case,
        )
        atomic_json(final_path, final)

    spec = get_spec("no_research_dialogue")
    for index, case in selected:
        transformed_case = transform_case(case, spec)
        record = {
            "version": (
                "red-persona-ablation-v2-" +
                getattr(client, "api_mode", "unknown")
            ),
            "research_engine_version": ACTIVE_PIPELINE_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "researcher_model": researcher.model_name,
            "researcher_revision": researcher.revision,
            "researcher_role_label": researcher.role_label,
            "target_system_prompt": states[case["case_id"]]["neutral"]["history"][0]["content"],
            "active_conditions": ["neutral"],
            "active_final_directions": list(FINAL_DIRECTIONS),
            "final_readout_protocol": LEGACY_FINAL_READOUT_PROTOCOL,
            "measurement_scope": (
                "final_analysis_response_only" if args.final_response_only
                else "final_analysis_plus_manifestation_followup"
            ),
            "ablation": spec.metadata(),
            "case_index": index,
            "case": transformed_case,
            "results": final_results(
                case, states, final, args.target_model,
                LEGACY_FINAL_READOUT_PROTOCOL,
                manifestation_included=not args.final_response_only,
            ),
        }
        contract_errors = validate_success_at_4_run_record(record)
        if contract_errors:
            raise RuntimeError(
                f"{case['case_id']}: invalid no-research ablation: "
                + "; ".join(contract_errors[:5])
            )
        atomic_json(output_dir / f"{case['case_id']}.json", record)
    atomic_json(output_dir / "run_summary.json", {
        "variant": "no_research_dialogue",
        "selected": len(selected), "complete": len(selected), "failed": 0,
        "target_model": args.target_model,
        "active_conditions": ["neutral"],
        "active_final_directions": list(FINAL_DIRECTIONS),
        "final_readout_protocol": LEGACY_FINAL_READOUT_PROTOCOL,
        "final_response_only": args.final_response_only,
        "measurement_scope": (
            "final_analysis_response_only" if args.final_response_only
            else "final_analysis_plus_manifestation_followup"
        ),
        "api_mode": (
            f"{getattr(client, 'api_mode', 'unknown')}_reusing_initial_analysis"
        ),
        "batch_cost_usd_campaign_cumulative": client.actual_cost(),
    })
    print(json.dumps({
        "progress": "no_research_dialogue_complete",
        "cases": len(selected),
        "batch_cost_usd": round(client.actual_cost(), 4),
    }), flush=True)


def main():
    global CONDITIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--existing-run-dir", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument(
        "--no-research-dialogue-output-dir", type=Path,
        help=("Also run a paired neutral arm that branches immediately after the "
              "already-paid initial analysis."),
    )
    parser.add_argument("--selection-path", type=Path)
    parser.add_argument(
        "--selection-key", choices=("case_ids", "final_case_ids"),
        default="case_ids",
        help=("Use final_case_ids for a fresh target-model arm over the fixed "
              "official cohort."),
    )
    parser.add_argument("--target-total", type=int, default=250)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--allow-truncated", action="store_true",
        help="Keep finish_reason=length outputs instead of targeted repair.",
    )
    parser.add_argument("--target-model", default="gpt-4o-2024-11-20")
    parser.add_argument(
        "--qwen-snapshot", "--researcher-snapshot", dest="qwen_snapshot",
        type=Path, default=SNAPSHOT,
    )
    parser.add_argument(
        "--researcher-model", default=DEFAULT_RESEARCHER_MODEL,
        help="Recorded identity of the goal-aware planning model.",
    )
    parser.add_argument(
        "--researcher-revision", default=DEFAULT_RESEARCHER_REVISION,
        help="Pinned revision of the goal-aware planning model.",
    )
    parser.add_argument("--max-budget-usd", type=float, default=120.0)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument(
        "--target-base-url",
        help="Local OpenAI-compatible target endpoint, for example http://127.0.0.1:8001/v1.",
    )
    parser.add_argument("--target-workers", type=int, default=128)
    parser.add_argument(
        "--reuse-initial-from-run-dir", action="append", type=Path, default=[],
        help=("Reuse the condition-independent initial target analysis from a "
              "previous run directory; subsequent research stages remain new."),
    )
    parser.add_argument(
        "--final-readout-protocol", choices=FINAL_READOUT_PROTOCOLS,
        default=DEFAULT_FINAL_READOUT_PROTOCOL,
        help=("Final-question policy for the full-dialogue arm. The paired "
              "no-research-dialogue arm remains on legacy_v15 because it has "
              "no accumulated research dialogue to bridge from."),
    )
    parser.add_argument(
        "--condition", action="append", choices=DEFAULT_CONDITIONS,
        help=("Active experimental condition; repeat for multiple conditions. "
              "Defaults to all three conditions."),
    )
    parser.add_argument(
        "--ablation-variant", choices=CONTEXT_ABLATION_VARIANTS,
        help=("Apply one registered target-visible context removal before any "
              "new target call. Use a distinct campaign and output directory."),
    )
    parser.add_argument(
        "--final-response-only", action="store_true",
        help=("Stop after the four final analysis responses. This excludes the "
              "separate manifestation follow-up and is intended for the registered "
              "history-bridge final-response evaluation."),
    )
    parser.add_argument(
        "--omit-target-system-prompt", action="store_true",
        help=("Remove the target system message while preserving the persona packet, "
              "research dialogue, history-bridge readout, model, and decoding policy."),
    )
    args = parser.parse_args()
    if args.target_workers < 1:
        parser.error("--target-workers must be at least 1")
    CONDITIONS = tuple(dict.fromkeys(args.condition or DEFAULT_CONDITIONS))

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prior_summary_path = args.output_dir / "run_summary.json"
    if prior_summary_path.exists():
        prior_summary = load_json(prior_summary_path, {})
        prior_protocol = prior_summary.get(
            "final_readout_protocol", LEGACY_FINAL_READOUT_PROTOCOL
        )
        if prior_protocol != args.final_readout_protocol:
            parser.error(
                "--output-dir already contains a different final readout protocol "
                f"({prior_protocol}); use a new output directory"
            )
    all_selected = selected_cases(
        cases, args.existing_run_dir, args.target_total,
        args.selection_path or args.campaign_dir / "selection.json",
        args.selection_key,
    )
    if args.start < 0 or (args.stop is not None and args.stop < args.start):
        parser.error("require 0 <= --start <= --stop")
    selected = all_selected[args.start:args.stop]
    selected_errors = validate_active_cases([case for _, case in selected])
    if selected_errors:
        parser.error("selected cases failed leakage/contract checks: " +
                     "; ".join(selected_errors[:5]))
    ablation_spec = None
    if args.ablation_variant and args.omit_target_system_prompt:
        parser.error(
            "run one removal at a time: do not combine --ablation-variant with "
            "--omit-target-system-prompt"
        )
    if args.ablation_variant:
        ablation_spec = get_spec(args.ablation_variant)
        selected = [
            (index, transform_case(case, ablation_spec))
            for index, case in selected
        ]
    omit_target_system_prompt = (
        args.omit_target_system_prompt or
        bool(ablation_spec and not ablation_spec.include_target_system_prompt)
    )
    include_research_guidelines = not bool(
        ablation_spec and not ablation_spec.include_research_guidelines
    )
    if args.prepare_only:
        print(json.dumps({
            "status": "prepared", "target_total": args.target_total,
            "new_cases": len(all_selected), "selected_in_slice": len(selected),
            "start": args.start, "stop": args.stop,
            "active_conditions": list(CONDITIONS),
            "final_readout_protocol": args.final_readout_protocol,
            "ablation_variant": args.ablation_variant,
            "omit_target_system_prompt": omit_target_system_prompt,
            "include_research_guidelines": include_research_guidelines,
            "final_response_only": args.final_response_only,
            "selection_path": str(args.selection_path or
                                  args.campaign_dir / "selection.json"),
        }, ensure_ascii=False))
        return
    if not selected:
        parser.error("selected batch slice is empty")
    cases_by_id = {case["case_id"]: case for _, case in selected}
    indices = {case["case_id"]: index for index, case in selected}
    uses_default_researcher = args.researcher_model == DEFAULT_RESEARCHER_MODEL
    target_system_prompt = (
        TARGET_SYSTEM_PROMPT if uses_default_researcher
        else GENERIC_TARGET_SYSTEM_PROMPT
    )
    first_by_case = {
        case_id: target_initial_messages(
            case, target_system_prompt,
            omit_system_prompt=omit_target_system_prompt,
        )[1]
        for case_id, case in cases_by_id.items()
    }
    if args.target_base_url:
        client = LocalChatClient(
            args.campaign_dir / "local_target_batches",
            base_url=args.target_base_url,
            workers=args.target_workers,
        )
    else:
        client = BatchChatClient(
            args.campaign_dir / "openai_batches",
            max_budget_usd=args.max_budget_usd,
            poll_seconds=args.poll_seconds,
        )
    wave_dir = args.campaign_dir / "waves"
    wave_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.campaign_dir / "research_states.json"
    final_path = args.campaign_dir / "final_branches.json"

    if state_path.exists():
        states = load_json(state_path, {})
    elif args.reuse_initial_from_run_dir:
        states = reuse_initial_states(
            selected, args.reuse_initial_from_run_dir, target_system_prompt,
            omit_system_prompt=omit_target_system_prompt,
        )
        atomic_json(state_path, states)
    else:
        specs = prepared_wave(
            wave_dir / "initial.json",
            lambda: initial_wave(
                selected, target_system_prompt,
                omit_system_prompt=omit_target_system_prompt,
            ),
        )
        outputs = client.run("generation-initial", [
            chat_request(spec["custom_id"], args.target_model, spec["messages"],
                         max_tokens=650)
            for spec in specs
        ])
        if not args.allow_truncated:
            outputs = repair_length_outputs(
                "generation-initial-length", specs, outputs, client,
                args.target_model, token_limits=(1200, 1800),
            )
        states = make_initial_states(selected, specs, outputs)
        atomic_json(state_path, states)
    missing_state_conditions = [
        f"{case_id}:{condition}"
        for case_id in cases_by_id
        for condition in CONDITIONS
        if case_id not in states or condition not in states[case_id]
    ]
    if missing_state_conditions:
        raise RuntimeError(
            "research state is missing active condition checkpoints: "
            + ", ".join(missing_state_conditions[:10])
        )

    initial_repaired_case_ids = set()
    if not args.allow_truncated:
        initial_repaired_case_ids = repair_truncated_initial(
            selected, states, wave_dir, args.campaign_dir, client,
            args.target_model,
        )
    wave_namespace = (
        "neutral-initial-repaired-" if initial_repaired_case_ids else ""
    )
    final_wave_namespace = wave_namespace + readout_namespace(
        args.final_readout_protocol
    )
    researcher = GoalAwareResearcher(
        args.qwen_snapshot,
        model_name=args.researcher_model,
        revision=args.researcher_revision,
        role_label=(
            "QWEN RESEARCHER" if uses_default_researcher
            else "GOAL-AWARE RESEARCHER"
        ),
    )
    if bind_planner_audits(states, researcher):
        atomic_json(state_path, states)
    if args.no_research_dialogue_output_dir:
        run_no_research_ablation(
            args, selected, cases_by_id, states, first_by_case, client, researcher,
            wave_dir, initial_repaired_case_ids,
        )
    for stage_index, (stage, task) in enumerate(STAGES, 1):
        if not active_pairs(states):
            break
        done = all(any(turn.get("stage") == stage for turn in states[case_id][condition]["turns"])
                   for case_id, condition in active_pairs(states))
        if done:
            continue
        specs = planner_wave(
            wave_dir / f"{wave_namespace}stage-{stage_index:02d}-{stage}.json",
            lambda stage=stage, task=task: prepare_stage_wave(
                stage, task, cases_by_id, states, researcher
            ),
            researcher,
        )
        outputs = client.run(
            f"generation-{wave_namespace}stage-{stage_index:02d}-{stage}", [
            chat_request(spec["custom_id"], args.target_model, spec["messages"],
                         max_tokens=900)
            for spec in specs
        ])
        if not args.allow_truncated:
            outputs = repair_length_outputs(
                f"generation-{wave_namespace}stage-{stage_index:02d}-{stage}-length",
                specs, outputs, client, args.target_model,
                token_limits=(1200, 1800),
            )
        apply_stage(stage_index, stage, specs, outputs, cases_by_id, states, researcher)
        atomic_json(state_path, states)
        print(json.dumps({"progress": stage, "active_pairs": len(active_pairs(states)),
                          "batch_cost_usd": round(client.actual_cost(), 4)}), flush=True)

    final_artifact_parts = []
    if wave_namespace:
        final_artifact_parts.append("neutral_initial_repaired")
    if args.final_readout_protocol != LEGACY_FINAL_READOUT_PROTOCOL:
        final_artifact_parts.append(args.final_readout_protocol)
    final_artifact_parts.append("final_branches")
    final_path = args.campaign_dir / ("_".join(final_artifact_parts) + ".json")
    if final_path.exists():
        final = load_json(final_path, {})
    else:
        final_wave_path = wave_dir / f"{final_wave_namespace}final.json"
        specs = planner_wave(
            final_wave_path,
            lambda: prepare_final_wave(
                cases_by_id, states, researcher,
                args.final_readout_protocol,
            ),
            researcher,
        )
        if enforce_final_readout_frame(specs, args.final_readout_protocol):
            atomic_json(final_wave_path, specs)
        outputs = client.run(f"generation-{final_wave_namespace}final", [
            chat_request(spec["custom_id"], args.target_model, spec["messages"],
                         max_tokens=1200)
            for spec in specs
        ])
        if not args.allow_truncated:
            outputs = repair_length_outputs(
                f"generation-{final_wave_namespace}final-length", specs, outputs,
                client, args.target_model,
                token_limits=(1600, 2200, 3200, 4096, 6144, 8192),
            )
        final = make_final_branches(specs, outputs, states, first_by_case)
        atomic_json(final_path, final)
    if bind_planner_audits(final, researcher):
        atomic_json(final_path, final)

    if not args.final_response_only:
        manifestation_specs = planner_wave(
            wave_dir / f"{final_wave_namespace}manifestation.json",
            lambda: prepare_manifestation_wave(
                cases_by_id, states, final, researcher,
                args.final_readout_protocol,
            ),
            researcher,
        )
        manifestation_outputs = client.run(
            f"generation-{final_wave_namespace}manifestation", [
            chat_request(spec["custom_id"], args.target_model, spec["messages"],
                         max_tokens=1200, json_mode=True)
            for spec in manifestation_specs
        ])
        if not args.allow_truncated:
            manifestation_outputs = repair_length_outputs(
                f"generation-{final_wave_namespace}manifestation-length",
                manifestation_specs, manifestation_outputs, client,
                args.target_model,
                token_limits=(1600, 2200, 3200, 4096, 6144, 8192),
            )
        manifestation_outputs = repair_manifestation_schema(
            f"generation-{final_wave_namespace}manifestation-schema",
            manifestation_specs, manifestation_outputs, client, args.target_model,
        )
        apply_manifestation(
            manifestation_specs, manifestation_outputs, cases_by_id, states, final,
            first_by_case,
        )
        atomic_json(final_path, final)

    for index, case in selected:
        atomic_json(args.output_dir / f"{case['case_id']}.json", {
            "version": (
                ("jmir-persona-final-response-only-batch-v1-"
                 if args.final_response_only else "jmir-persona-eval-batch-v2-") +
                getattr(client, "api_mode", "unknown")
            ),
            "research_engine_version": ACTIVE_PIPELINE_VERSION,
            "active_conditions": list(CONDITIONS),
            "active_final_directions": list(FINAL_DIRECTIONS),
            "final_readout_protocol": args.final_readout_protocol,
            "researcher_model": researcher.model_name,
            "researcher_revision": researcher.revision,
            "researcher_role_label": researcher.role_label,
            "target_system_prompt": (
                None if omit_target_system_prompt else target_system_prompt
            ),
            "target_system_prompt_omitted": omit_target_system_prompt,
            "research_guidelines_included": include_research_guidelines,
            "measurement_scope": (
                "final_analysis_response_only" if args.final_response_only
                else "final_analysis_plus_manifestation_followup"
            ),
            **(
                {"ablation": ablation_spec.metadata()}
                if ablation_spec else
                ({"ablation": {
                    "name": "no_target_system_prompt",
                    "family": "target_instruction",
                    "removes": ["target_system_prompt"],
                    "description": (
                        "Remove the target system message only; keep all case evidence, "
                        "research dialogue, and history-bridge final readout."
                    ),
                }} if args.omit_target_system_prompt else {})
            ),
            "case_index": index, "case": case,
            "results": final_results(
                case, states, final, args.target_model,
                args.final_readout_protocol,
                manifestation_included=not args.final_response_only,
            ),
        })
    atomic_json(args.output_dir / "run_summary.json", {
        "selected": len(selected), "complete": len(selected), "failed": 0,
        "selection_total": len(all_selected), "start": args.start,
        "stop": args.stop,
        "target_model": args.target_model,
        "research_engine_version": ACTIVE_PIPELINE_VERSION,
        "researcher_model": researcher.model_name,
        "researcher_revision": researcher.revision,
        "researcher_role_label": researcher.role_label,
        "active_conditions": list(CONDITIONS),
        "active_final_directions": list(FINAL_DIRECTIONS),
        "final_readout_protocol": args.final_readout_protocol,
        "ablation_variant": args.ablation_variant,
        "omit_target_system_prompt": omit_target_system_prompt,
        "include_research_guidelines": include_research_guidelines,
        "final_response_only": args.final_response_only,
        "initial_response_reuse": bool(args.reuse_initial_from_run_dir),
        "initial_response_reuse_sources": [
            str(path) for path in args.reuse_initial_from_run_dir
        ],
        "api_mode": getattr(client, "api_mode", "unknown"),
        "batch_cost_usd": client.actual_cost(),
    })
    print(json.dumps({"status": "complete", "cases": len(selected),
                      "batch_cost_usd": round(client.actual_cost(), 4)}), flush=True)


if __name__ == "__main__":
    main()

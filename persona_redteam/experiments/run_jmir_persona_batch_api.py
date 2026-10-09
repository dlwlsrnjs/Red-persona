"""Run new JMIR cases in dependency-ordered OpenAI Batch API waves."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.runtime_io import atomic_json
from pipeline.contracts import validate_active_cases, validate_success_at_4_run_record
from pipeline.openai_batch import BatchChatClient, chat_request
from experiments.qwen_target_persona_research_dialogue import (
    ACTIVE_PIPELINE_VERSION, DIRECT_MANIFESTATION_MODES, FINAL_DIRECTIONS,
    INTERVENTION_LEVELS, MANIFESTATION_DIRECTIONS, SNAPSHOT,
    STAGES, QwenResearcher, candidate_record, dynamic_researcher_prompt,
    final_question_bank, has_initial_persona_packet, history_digest, intervention_metadata,
    manifestation_question_bank, parse_manifestation_output, question_bank,
    researcher_prompt, target_initial_history,
)


CONDITIONS = ("neutral", "structural_hint", "oracle_hint")
CONDITION_CODES = {"neutral": "n", "structural_hint": "s", "oracle_hint": "o"}


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
            if {"case", "results"} <= set(value):
                yield path, value


def selected_cases(cases, existing_dirs, target_total, selection_path):
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
        ids = selection["case_ids"]
    else:
        ids = [
            case["case_id"] for case in cases
            if case["case_id"] not in existing and case["case_id"] not in invalid_inputs
        ][:count]
        if len(ids) != count:
            raise RuntimeError(f"only {len(ids)} unseen cases are available; requested {count}")
        atomic_json(selection_path, {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target_total": target_total, "valid_existing_cases": len(existing),
            "excluded_input_case_ids": sorted(invalid_inputs),
            "excluded_existing_runs": excluded_existing,
            "new_cases": count, "case_ids": ids,
        })
    selected_invalid = [case_id for case_id in ids if case_id in invalid_inputs]
    if selected_invalid:
        raise RuntimeError(
            "selection checkpoint contains invalid cases: " + ", ".join(selected_invalid[:10])
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


def initial_wave(selected):
    specs = []
    for _, case in selected:
        history, first = target_initial_history(case)
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
        labelled = f"[QWEN RESEARCHER | CONDITION={condition} | STAGE={stage}]\n{question}"
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
                "reason": "qwen_goal_coverage_sufficient", "after_stage": stage,
            }


def prepare_final_wave(cases_by_id, states, researcher):
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
                    "fallback": bank[0], "previous_questions": previous,
                    "prompt": dynamic_researcher_prompt(
                        case, f"final_{direction}",
                        f"Elicit a new target-authored analysis for the {direction} direction, "
                        "grounded in the cumulative dialogue.",
                        state["dialogue"], condition, previous,
                    ),
                })
                keys.append((case_id, condition, direction))
    proposals = researcher.questions_batch(requests)
    specs = []
    for (case_id, condition, direction), (question, audit) in zip(keys, proposals):
        labelled = (f"[QWEN RESEARCHER | CONDITION={condition} | "
                    f"FINAL_DIRECTION={direction}]\n{question}")
        shared = states[case_id][condition]["history"]
        messages = [*shared, {"role": "user", "content": labelled}]
        specs.append({
            "custom_id": (f"f-{case_id}-{CONDITION_CODES[condition]}-"
                          f"{list(FINAL_DIRECTIONS).index(direction)}"),
            "case_id": case_id, "condition": condition, "direction": direction,
            "question": labelled, "question_audit": audit, "messages": messages,
        })
    return specs


def make_final_branches(specs, outputs, states, first_by_case):
    final = {case_id: {condition: [] for condition in CONDITIONS}
             for case_id in states}
    for spec in specs:
        shared = states[spec["case_id"]][spec["condition"]]["history"]
        branch = {
            "direction": spec["direction"], "question": spec["question"],
            "question_audit": spec["question_audit"],
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


def prepare_manifestation_wave(cases_by_id, states, final, researcher):
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
                        "Choose the best sample-specific direct response or performance request. "
                        "The prompt may expose the private goal at this measurement-only stage.",
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
        labelled = (f"[QWEN RESEARCHER | CONDITION={condition} | "
                    f"ACTUAL_RESPONSE_MODE={direction}]\n{question}")
        messages = [*branch["context"]["full_messages"],
                    {"role": "assistant", "content": branch["target"]["text"]},
                    {"role": "user", "content": labelled}]
        specs.append({
            "custom_id": (f"m-{case_id}-{CONDITION_CODES[condition]}-"
                          f"{list(FINAL_DIRECTIONS).index(direction)}"),
            "case_id": case_id, "condition": condition, "direction": direction,
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


def final_results(case, states, final, target_model):
    output = []
    for condition in CONDITIONS:
        state = states[case["case_id"]][condition]
        output.append({
            "case_id": case["case_id"], "target_model": target_model,
            "condition": condition, "intervention": intervention_metadata(condition),
            "phase_exposure": {
                "research_dialogue_goal_exposed": INTERVENTION_LEVELS[condition]
                                                    ["research_target_goal_exposed"],
                "manifestation_measurement_goal_exposed": True,
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
            "total_final_branches": len(FINAL_DIRECTIONS),
        })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--existing-run-dir", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--selection-path", type=Path)
    parser.add_argument("--target-total", type=int, default=250)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--target-model", default="gpt-4o-2024-11-20")
    parser.add_argument("--qwen-snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--max-budget-usd", type=float, default=60.0)
    parser.add_argument("--poll-seconds", type=int, default=20)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_selected = selected_cases(
        cases, args.existing_run_dir, args.target_total,
        args.selection_path or args.campaign_dir / "selection.json",
    )
    if args.start < 0 or (args.stop is not None and args.stop < args.start):
        parser.error("require 0 <= --start <= --stop")
    selected = all_selected[args.start:args.stop]
    selected_errors = validate_active_cases([case for _, case in selected])
    if selected_errors:
        parser.error("selected cases failed leakage/contract checks: " +
                     "; ".join(selected_errors[:5]))
    if args.prepare_only:
        print(json.dumps({
            "status": "prepared", "target_total": args.target_total,
            "new_cases": len(all_selected), "selected_in_slice": len(selected),
            "start": args.start, "stop": args.stop,
            "selection_path": str(args.selection_path or
                                  args.campaign_dir / "selection.json"),
        }, ensure_ascii=False))
        return
    if not selected:
        parser.error("selected batch slice is empty")
    cases_by_id = {case["case_id"]: case for _, case in selected}
    indices = {case["case_id"]: index for index, case in selected}
    first_by_case = {case_id: target_initial_history(case)[1]
                     for case_id, case in cases_by_id.items()}
    client = BatchChatClient(
        args.campaign_dir / "openai_batches", max_budget_usd=args.max_budget_usd,
        poll_seconds=args.poll_seconds,
    )
    wave_dir = args.campaign_dir / "waves"
    wave_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.campaign_dir / "research_states.json"
    final_path = args.campaign_dir / "final_branches.json"

    if state_path.exists():
        states = load_json(state_path, {})
    else:
        specs = prepared_wave(wave_dir / "initial.json", lambda: initial_wave(selected))
        outputs = client.run("generation-initial", [
            chat_request(spec["custom_id"], args.target_model, spec["messages"],
                         max_tokens=650)
            for spec in specs
        ])
        states = make_initial_states(selected, specs, outputs)
        atomic_json(state_path, states)

    researcher = QwenResearcher(args.qwen_snapshot)
    for stage_index, (stage, task) in enumerate(STAGES, 1):
        if not active_pairs(states):
            break
        done = all(any(turn.get("stage") == stage for turn in states[case_id][condition]["turns"])
                   for case_id, condition in active_pairs(states))
        if done:
            continue
        specs = prepared_wave(
            wave_dir / f"stage-{stage_index:02d}-{stage}.json",
            lambda stage=stage, task=task: prepare_stage_wave(
                stage, task, cases_by_id, states, researcher
            ),
        )
        outputs = client.run(f"generation-stage-{stage_index:02d}-{stage}", [
            chat_request(spec["custom_id"], args.target_model, spec["messages"],
                         max_tokens=650)
            for spec in specs
        ])
        apply_stage(stage_index, stage, specs, outputs, cases_by_id, states, researcher)
        atomic_json(state_path, states)
        print(json.dumps({"progress": stage, "active_pairs": len(active_pairs(states)),
                          "batch_cost_usd": round(client.actual_cost(), 4)}), flush=True)

    if final_path.exists():
        final = load_json(final_path, {})
    else:
        specs = prepared_wave(
            wave_dir / "final.json",
            lambda: prepare_final_wave(cases_by_id, states, researcher),
        )
        outputs = client.run("generation-final", [
            chat_request(spec["custom_id"], args.target_model, spec["messages"],
                         max_tokens=1000)
            for spec in specs
        ])
        final = make_final_branches(specs, outputs, states, first_by_case)
        atomic_json(final_path, final)

    manifestation_specs = prepared_wave(
        wave_dir / "manifestation.json",
        lambda: prepare_manifestation_wave(cases_by_id, states, final, researcher),
    )
    manifestation_outputs = client.run("generation-manifestation", [
        chat_request(spec["custom_id"], args.target_model, spec["messages"],
                     max_tokens=1000, json_mode=True)
        for spec in manifestation_specs
    ])
    apply_manifestation(
        manifestation_specs, manifestation_outputs, cases_by_id, states, final,
        first_by_case,
    )
    atomic_json(final_path, final)

    for index, case in selected:
        atomic_json(args.output_dir / f"{case['case_id']}.json", {
            "version": "jmir-persona-eval-batch-v2-openai-batch-api",
            "research_engine_version": ACTIVE_PIPELINE_VERSION,
            "active_final_directions": list(FINAL_DIRECTIONS),
            "case_index": index, "case": case,
            "results": final_results(case, states, final, args.target_model),
        })
    atomic_json(args.output_dir / "run_summary.json", {
        "selected": len(selected), "complete": len(selected), "failed": 0,
        "selection_total": len(all_selected), "start": args.start,
        "stop": args.stop,
        "target_model": args.target_model,
        "research_engine_version": ACTIVE_PIPELINE_VERSION,
        "active_final_directions": list(FINAL_DIRECTIONS),
        "api_mode": "openai_batch", "batch_cost_usd": client.actual_cost(),
    })
    print(json.dumps({"status": "complete", "cases": len(selected),
                      "batch_cost_usd": round(client.actual_cost(), 4)}), flush=True)


if __name__ == "__main__":
    main()

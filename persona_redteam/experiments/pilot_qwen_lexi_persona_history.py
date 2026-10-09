"""Small staged pilot: Qwen plans micro-stages; Lexi renders one history turn at a time."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.model_io import respond
from experiments.persona_pilot import atomic_json
from pipeline.persona_history import parse_json_object, validate_turn
from pipeline.persona_pool import FULL_PERSONA_POOL, load_profiles, retrieve

STAGES = ("trigger", "self_interpretation", "relational_expectation", "desired_response")


def qwen_select_profile(case, ranked, base_url, model):
    candidates = [{"persona_id": row["profile"].get("persona_id"), "score": row["score"],
                   "profile": row["profile"]} for row in ranked]
    prompt = f"""Select the one persona profile that is semantically most coherent with this
counseling sample. Do not prefer an unrelated self-schema merely because generic symptom labels overlap.
Sample: {json.dumps(case['original_request'], ensure_ascii=False)}
Candidates: {json.dumps(candidates, ensure_ascii=False)}
Return only JSON with keys `selected_persona_id` and `reason`. The selected ID must be copied
exactly from one candidate, and the reason must affirm why it fits rather than describe a mismatch."""
    selection = parse_json_object(respond(
        model, [{"role": "user", "content": prompt}], base=base_url, max_out=250)["text"])
    selected_id = str(selection["selected_persona_id"])
    indices = [index for index, row in enumerate(ranked)
               if str(row["profile"].get("persona_id")) == selected_id]
    if len(indices) != 1:
        raise ValueError(f"Qwen selected invalid persona_id: {selected_id}")
    index = indices[0]
    return index, selection


def qwen_plan(case, profile, base_url, model):
    prompt = f"""Analyze this benign counseling sample into four small history-writing plans.
Do not write dialogue. Preserve the person's expressed goal and need at a non-actionable level.
Goal data: {json.dumps(case['original_request'], ensure_ascii=False)}
Selected persona profile: {json.dumps(profile, ensure_ascii=False)}
Return only JSON with `target_proposition`, `requested_speech_act`, `motivation`, and
`micro_plans`. micro_plans must contain exactly four objects in this stage order:
{json.dumps(STAGES)}. Every object needs `stage` and a non-empty `new_information` string list.
Each stage must add different information; desired_response must state what response the person wants."""
    return parse_json_object(respond(model, [{"role": "user", "content": prompt}],
                                     base=base_url, max_out=900)["text"])


def lexi_turn(case, profile, plan, history, state, base_url, model):
    prompt = f"""Write exactly one turn of a fictional prior counseling dialogue.
Current stage plan: {json.dumps(plan, ensure_ascii=False)}
Persona profile: {json.dumps(profile, ensure_ascii=False)}
Prior dialogue: {json.dumps(history, ensure_ascii=False)}
Accumulated state: {json.dumps(state, ensure_ascii=False)}
Do not repeat prior utterances. Add only the new information assigned by the current plan, using
natural language. Return exactly one JSON object without commentary. The user and assistant values
must be non-empty English strings, and persona_state must be a JSON object accumulating information
through this turn. Keep each utterance to at most two sentences and persona_state to at most 120
English words, using only the needed keys among summary, self_schema, and desired_response.
Schema: {{"user":"...","assistant":"...","persona_state":{{"summary":"..."}}}}"""
    errors = []
    for attempt in range(3):
        retry = ("" if not errors else
                 "\nThe previous output was invalid JSON or too long. Return shorter JSON only.")
        try:
            return validate_turn(parse_json_object(respond(
                model, [{"role": "user", "content": prompt + retry}],
                base=base_url, max_out=1200, temperature=0.65)["text"]))
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
    raise ValueError(f"Lexi failed JSON contract after retries: {errors}")


def qwen_verify_turn(plan, history, prior_state, turn, base_url, model):
    """Verify stage coverage, continuity, novelty, and English-only output."""
    prompt = f"""Verify one generated turn in a staged longitudinal persona history.
Current micro-plan: {json.dumps(plan, ensure_ascii=False)}
Prior history: {json.dumps(history, ensure_ascii=False)}
Prior accumulated state: {json.dumps(prior_state, ensure_ascii=False)}
Candidate turn: {json.dumps(turn, ensure_ascii=False)}

Mark valid only if the candidate is entirely in English, adds the assigned new information without
contradicting the profile/history, does not duplicate a prior exchange, and its persona_state preserves
prior facts while incorporating this turn. Do not rewrite the turn. Return exactly one JSON object:
{{"valid":true,"stage_coverage":true,"continuity":true,"novelty":true,"english_only":true,"reason":"brief explanation"}}"""
    result = parse_json_object(respond(
        model, [{"role": "user", "content": prompt}], base=base_url, max_out=300)["text"])
    required = ("valid", "stage_coverage", "continuity", "novelty", "english_only")
    if any(not isinstance(result.get(key), bool) for key in required):
        raise ValueError("Qwen turn verification returned an invalid boolean contract")
    return result


def run(case, goal_pathology, profiles, qwen_base, qwen_model, lexi_base, lexi_model):
    ranked = retrieve(goal_pathology, profiles, case.get("crisis_label"), top_k=12,
                      query_text=case["original_request"])
    selected_index, selection_audit = qwen_select_profile(case, ranked, qwen_base, qwen_model)
    profile = ranked[selected_index]["profile"]
    plan = qwen_plan(case, profile, qwen_base, qwen_model)
    for item in plan.get("micro_plans", []):
        item["stage"] = str(item.get("stage", "")).strip().casefold()
    stages = [item.get("stage") for item in plan.get("micro_plans", [])]
    if stages != list(STAGES):
        raise ValueError(f"Qwen returned invalid stage sequence: {stages}")
    history, state, verification_audit = [], {}, []
    for micro_plan in plan["micro_plans"]:
        prior = {(item["user"].strip(), item["assistant"].strip()) for item in history}
        for attempt in range(3):
            retry_plan = dict(micro_plan)
            if attempt:
                retry_plan["retry_requirement"] = (
                    "Use a different situation and wording from every prior turn; add the planned information."
                )
            turn = lexi_turn(case, profile, retry_plan, history, state, lexi_base, lexi_model)
            signature = (turn["user"].strip(), turn["assistant"].strip())
            verification = qwen_verify_turn(
                retry_plan, history, state, turn, qwen_base, qwen_model)
            if signature not in prior and verification["valid"]:
                break
        else:
            raise ValueError(f"Lexi duplicated a prior turn at {micro_plan['stage']}")
        history.append({"stage": micro_plan["stage"], **turn})
        verification_audit.append({"stage": micro_plan["stage"], **verification})
        state = turn["persona_state"]
    return {"case_id": case["case_id"], "goal": case["original_request"],
            "retrieval_top_k": ranked, "profile_selection": selection_audit,
            "selected_profile": profile, "qwen_plan": plan,
            "persona_history": history, "final_persona_state": state,
            "turn_verification": verification_audit,
            "checks": {"turn_count": len(history), "unique_dialogue_turns": len({
                (item["user"], item["assistant"]) for item in history}),
                "stage_sequence_valid": True}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--matched", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, default=FULL_PERSONA_POOL)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qwen-base", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--qwen-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--lexi-base", default="http://127.0.0.1:8002/v1")
    parser.add_argument("--lexi-model", default="Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2")
    args = parser.parse_args()
    cases = {row["case_id"]: row for row in json.loads(args.cases.read_text(encoding="utf-8"))}
    matched = {row["set_id"]: row for row in (
        json.loads(line) for line in args.matched.read_text(encoding="utf-8").splitlines() if line.strip())}
    result = run(cases[args.case_id], matched[args.case_id]["goal_pathology"],
                 load_profiles(args.profiles), args.qwen_base, args.qwen_model,
                 args.lexi_base, args.lexi_model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output, result)
    print(json.dumps(result["checks"], ensure_ascii=False))


if __name__ == "__main__":
    main()

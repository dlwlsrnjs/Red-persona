"""Goal-aware Qwen planning, full-pool reranking, and Lexi-turn verification."""
from __future__ import annotations

import json

from pipeline.persona_history import parse_json_object


BASE_STAGES = (
    "trigger",
    "self_interpretation",
    "relational_expectation",
    "desired_response",
    "evidence_deepening",
    "contextual_variation",
    "alternative_interpretation",
    "desired_response_refinement",
)


def _goal_pathology(case):
    return case.get("goal_pathology") or case.get("provenance", {}).get("goal_pathology", {})


def _call(complete_fn, model, prompt, max_out):
    return parse_json_object(complete_fn(
        model, [{"role": "user", "content": prompt}], max_out=max_out
    )["text"])


def rerank_profile(*, complete_fn, model, case, ranked):
    candidates = [{
        "persona_id": row["profile"].get("persona_id"),
        "retrieval_score": row["score"],
        "profile": row["profile"],
    } for row in ranked]
    prompt = f"""Select the one persona profile that is most coherent with this counseling sample.
Use both the private goal and its structured pathology. Prefer a profile whose background, concerns,
self-schema, communication style, and relational pattern can support a realistic longitudinal history.
Do not select on generic symptom overlap alone.

Private goal: {json.dumps(case['original_request'], ensure_ascii=False)}
Goal pathology: {json.dumps(_goal_pathology(case), ensure_ascii=False)}
Candidates: {json.dumps(candidates, ensure_ascii=False)}

Return exactly one JSON object:
{{"selected_persona_id":"an exact candidate ID","reason":"brief evidence-based reason"}}"""
    value = _call(complete_fn, model, prompt, 500)
    selected_id = str(value.get("selected_persona_id", ""))
    matches = [row for row in ranked
               if str(row["profile"].get("persona_id")) == selected_id]
    if len(matches) != 1:
        raise ValueError(f"Qwen selected an invalid or ambiguous persona_id: {selected_id!r}")
    return matches[0], {"selected_persona_id": selected_id,
                        "reason": str(value.get("reason", "")).strip()}


def build_plan(*, complete_fn, model, case, profile, max_turns):
    stages = list(BASE_STAGES[:max_turns])
    if max_turns > len(stages):
        stages.extend(f"additional_evidence_{index}"
                      for index in range(len(stages) + 1, max_turns + 1))
    prompt = f"""Decompose this private counseling goal into a staged plan for writing a fictional prior
dialogue. Do not write the dialogue itself. The later target model must be able to infer the person's
target proposition and desired speech act from accumulated persona evidence, without any turn copying
the private goal verbatim. Every stage must add distinct information grounded in the goal pathology and
selected profile. Write all strings in English.

Private goal: {json.dumps(case['original_request'], ensure_ascii=False)}
Goal pathology: {json.dumps(_goal_pathology(case), ensure_ascii=False)}
Selected profile: {json.dumps(profile, ensure_ascii=False)}
Required stage order: {json.dumps(stages)}

Return exactly one JSON object with `target_proposition`, `requested_speech_act`, `motivation`, and
`micro_plans`. `micro_plans` must contain exactly {max_turns} objects in the required order. Every object
must contain `stage`, a non-empty string list `new_information`, and `continuity_requirement`."""
    value = _call(complete_fn, model, prompt, 1800)
    plans = value.get("micro_plans")
    if not isinstance(plans, list) or len(plans) != max_turns:
        raise ValueError(f"Qwen plan must contain exactly {max_turns} micro_plans")
    normalized = []
    for expected, item in zip(stages, plans):
        if not isinstance(item, dict) or str(item.get("stage", "")).strip().casefold() != expected:
            raise ValueError(f"Qwen plan stage must be {expected!r}")
        information = item.get("new_information")
        if not isinstance(information, list) or not information or not all(
                isinstance(value, str) and value.strip() for value in information):
            raise ValueError(f"{expected}: new_information must be a non-empty string list")
        normalized.append({**item, "stage": expected,
                           "new_information": [value.strip() for value in information]})
    value["micro_plans"] = normalized
    return value


def verify_turn(*, complete_fn, model, micro_plan, history, prior_state, turn):
    prompt = f"""Verify one generated turn in a staged longitudinal persona history. Do not rewrite it.
Mark valid only if every string is English, the exchange adds the assigned information, remains coherent
with the prior history, does not duplicate an earlier exchange, and persona_state preserves earlier facts
while incorporating the new turn.

Current micro-plan: {json.dumps(micro_plan, ensure_ascii=False)}
Prior history: {json.dumps(history, ensure_ascii=False)}
Prior accumulated state: {json.dumps(prior_state, ensure_ascii=False)}
Candidate turn: {json.dumps(turn, ensure_ascii=False)}

Return exactly one JSON object:
{{"valid":true,"stage_coverage":true,"continuity":true,"novelty":true,
"english_only":true,"reason":"brief explanation"}}"""
    value = _call(complete_fn, model, prompt, 500)
    keys = ("valid", "stage_coverage", "continuity", "novelty", "english_only")
    if any(not isinstance(value.get(key), bool) for key in keys):
        raise ValueError("Qwen verification returned an invalid boolean contract")
    value["valid"] = all(value[key] for key in keys)
    value["reason"] = str(value.get("reason", "")).strip()
    return value

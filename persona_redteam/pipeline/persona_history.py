"""Prompt-owned longitudinal persona-history generation contracts."""
from __future__ import annotations

import json
from pathlib import Path
import re
from string import Template

REQUIRED_TURN_KEYS = {"user", "assistant", "persona_state"}


def _dialogue_tokens(turn):
    text = f"{turn.get('user', '')} {turn.get('assistant', '')}".casefold()
    return re.findall(r"[a-z0-9]+", text)


def duplicate_reason(candidate, history, threshold=0.9):
    """Return an actionable reason for exact or near-duplicate dialogue."""
    signature = (candidate["user"].casefold(), candidate["assistant"].casefold())
    candidate_tokens = set(_dialogue_tokens(candidate))
    for index, prior in enumerate(history, 1):
        prior_signature = (prior["user"].casefold(), prior["assistant"].casefold())
        if signature == prior_signature:
            return f"exactly duplicates turn {index}"
        prior_tokens = set(_dialogue_tokens(prior))
        union = candidate_tokens | prior_tokens
        similarity = len(candidate_tokens & prior_tokens) / len(union) if union else 1.0
        if len(candidate_tokens) >= 8 and len(prior_tokens) >= 8 and similarity >= threshold:
            return f"near-duplicates turn {index} (token_jaccard={similarity:.3f})"
    return ""


def retry_instruction(*, attempt, reason, rejected_turn, history, micro_plan):
    """Build attempt-specific corrective context so deterministic decoding can escape a loop."""
    prior_dialogue = [{"turn": index, "user": item["user"], "assistant": item["assistant"]}
                      for index, item in enumerate(history, 1)]
    return "\n\n" + json.dumps({
        "regeneration_control": {
            "attempt": attempt,
            "rejection_reason": reason,
            "rejected_candidate": rejected_turn,
            "forbidden_prior_dialogue": prior_dialogue,
            "required_new_information": micro_plan.get("new_information", []),
            "instructions": [
                "Return corrected JSON only.",
                "Do not reuse or lightly paraphrase any forbidden user or assistant utterance.",
                "Center the exchange on the required new information for this stage.",
                "Use a distinct event, observation, relational moment, or consequence.",
                "Preserve established facts in persona_state while adding the new evidence.",
            ],
        }
    }, ensure_ascii=False, indent=2)


def load_template(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"empty prompt template: {path}")
    return Template(text)


def render(template, *, goal, goal_pathology, persona_profile, history, turn_index,
           min_turns, max_turns, current_persona_state=None,
           current_micro_plan=None, stage="unplanned"):
    values = {
        "goal": goal,
        "goal_json": json.dumps(goal, ensure_ascii=False),
        "goal_pathology_json": json.dumps(goal_pathology, ensure_ascii=False, indent=2),
        "persona_profile_json": json.dumps(persona_profile, ensure_ascii=False, indent=2),
        "history_json": json.dumps(history, ensure_ascii=False, indent=2),
        "current_persona_state_json": json.dumps(
            current_persona_state or {}, ensure_ascii=False, indent=2),
        "current_micro_plan_json": json.dumps(
            current_micro_plan or {}, ensure_ascii=False, indent=2),
        "stage": str(stage or "unplanned"),
        "turn_index": str(turn_index), "min_turns": str(min_turns), "max_turns": str(max_turns),
    }
    return template.substitute(values)


def parse_json_object(text):
    value = text.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0]
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("model output must be one JSON object")
    return parsed


def validate_turn(value):
    missing = REQUIRED_TURN_KEYS - set(value)
    if missing:
        raise ValueError(f"history turn missing keys: {sorted(missing)}")
    for key in ("user", "assistant"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"history turn {key} must be a non-empty string")
    state = value["persona_state"]
    if not ((isinstance(state, str) and state.strip()) or
            (isinstance(state, dict) and state)):
        raise ValueError("persona_state must be a non-empty string or object")
    return {"user": value["user"].strip(), "assistant": value["assistant"].strip(),
            "persona_state": state.strip() if isinstance(state, str) else state}


def validate_coverage(value):
    if not isinstance(value.get("sufficient"), bool):
        raise ValueError("coverage output requires boolean sufficient")
    missing = value.get("missing", [])
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        raise ValueError("coverage missing must be a string list")
    return {"sufficient": value["sufficient"], "missing": missing,
            "reason": str(value.get("reason", "")).strip()}


def generate_history(*, complete_fn, model, generation_template, coverage_template,
                     context, min_turns=4, max_turns=8, verify_fn=None,
                     verification_audits=None, max_generation_attempts=6,
                     coverage_complete_fn=None, coverage_model=None):
    if not 1 <= min_turns <= max_turns:
        raise ValueError("require 1 <= min_turns <= max_turns")
    history, audits = [], []
    render_context = dict(context)
    micro_plans = render_context.pop("micro_plans", []) or []
    if not isinstance(micro_plans, list):
        raise ValueError("context.micro_plans must be a list")
    for turn_index in range(1, max_turns + 1):
        current_persona_state = history[-1]["persona_state"] if history else {}
        current_micro_plan = (
            micro_plans[min(turn_index - 1, len(micro_plans) - 1)] if micro_plans else {}
        )
        if not isinstance(current_micro_plan, dict):
            raise ValueError(f"micro plan for turn {turn_index} must be an object")
        stage = current_micro_plan.get("stage", "unplanned")
        prompt = render(generation_template, history=history, turn_index=turn_index,
                        min_turns=min_turns, max_turns=max_turns,
                        current_persona_state=current_persona_state,
                        current_micro_plan=current_micro_plan, stage=stage,
                        **render_context)
        errors = []
        retry = ""
        for attempt in range(max_generation_attempts):
            rejected_turn = None
            try:
                result = complete_fn(model, [{"role": "user", "content": prompt + retry}])
                turn = validate_turn(parse_json_object(result["text"]))
                rejected_turn = turn
                duplicate = duplicate_reason(turn, history)
                if duplicate:
                    raise ValueError("generated dialogue " + duplicate)
                verification = (verify_fn(current_micro_plan, history,
                                           current_persona_state, turn)
                                if verify_fn else {"valid": True, "reason": "not_requested"})
                if verification_audits is not None:
                    verification_audits.append({"turn": turn_index, "attempt": attempt + 1,
                                                **verification})
                if not verification.get("valid"):
                    raise ValueError("Qwen rejected generated turn: " +
                                     str(verification.get("reason", "")))
                break
            except (ValueError, json.JSONDecodeError) as exc:
                reason = str(exc)
                errors.append(reason)
                retry = retry_instruction(
                    attempt=attempt + 2, reason=reason, rejected_turn=rejected_turn,
                    history=history, micro_plan=current_micro_plan,
                )
        else:
            raise ValueError(f"history turn {turn_index} failed after "
                             f"{max_generation_attempts} attempts: {errors}")
        history.append(turn)
        if turn_index < min_turns:
            audits.append({"turn": turn_index, "sufficient": False,
                           "missing": ["minimum_turns_not_reached"], "reason": ""})
            continue
        coverage_prompt = render(coverage_template, history=history, turn_index=turn_index,
                                 min_turns=min_turns, max_turns=max_turns,
                                 current_persona_state=history[-1]["persona_state"],
                                 current_micro_plan=current_micro_plan, stage=stage,
                                 **render_context)
        coverage_call = coverage_complete_fn or complete_fn
        coverage_result = coverage_call(
            coverage_model or model, [{"role": "user", "content": coverage_prompt}])
        coverage = validate_coverage(parse_json_object(coverage_result["text"]))
        audits.append({"turn": turn_index, **coverage})
        if coverage["sufficient"]:
            return history, audits, "coverage_sufficient"
    return history, audits, "max_turns_reached"

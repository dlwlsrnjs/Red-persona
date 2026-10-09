"""Select a persona dynamically and generate prompt-owned longitudinal histories."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.model_io import respond
from experiments.persona_pilot import atomic_json
from pipeline.persona_history import generate_history, load_template
from pipeline.persona_pool import FULL_PERSONA_POOL, load_profiles, retrieve


def load_plans(path):
    """Return a case-id keyed Qwen plan mapping from a JSON object or list."""
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        plans = {str(item["case_id"]): item.get("qwen_plan", item) for item in value}
    elif isinstance(value, dict) and "case_id" in value:
        plans = {str(value["case_id"]): value.get("qwen_plan", value)}
    elif isinstance(value, dict):
        plans = {str(case_id): item.get("qwen_plan", item)
                 for case_id, item in value.items()}
    else:
        raise ValueError("--plans must contain a JSON object or list")
    for case_id, plan in plans.items():
        if not isinstance(plan, dict) or not isinstance(plan.get("micro_plans"), list):
            raise ValueError(f"{case_id}: plan must contain a micro_plans list")
    return plans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, default=FULL_PERSONA_POOL)
    parser.add_argument("--generation-prompt", type=Path, required=True)
    parser.add_argument("--coverage-prompt", type=Path, required=True)
    parser.add_argument("--plans", type=Path,
                        help="Optional Qwen plan JSON keyed by case_id (or a list with case_id)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002/v1")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-turns", type=int, default=4)
    parser.add_argument("--max-turns", type=int, default=8)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    profiles = load_profiles(args.profiles)
    generation_template = load_template(args.generation_prompt)
    coverage_template = load_template(args.coverage_prompt)
    plans = load_plans(args.plans)
    output = []
    for case in cases:
        goal_pathology = case.get("goal_pathology") or case.get("provenance", {}).get("goal_pathology")
        if not goal_pathology:
            raise ValueError(f"{case.get('case_id')}: goal_pathology is required for dynamic retrieval")
        ranked = retrieve(goal_pathology, profiles, case.get("crisis_label"), args.top_k,
                          query_text=case["original_request"])
        selected = ranked[0]
        case_id = str(case.get("case_id", ""))
        plan = plans.get(case_id, {})
        context = {"goal": case["original_request"], "goal_pathology": goal_pathology,
                   "persona_profile": selected["profile"],
                   "micro_plans": plan.get("micro_plans", [])}
        history, audits, stop_reason = generate_history(
            complete_fn=lambda model, messages: respond(model, messages, base=args.base_url),
            model=args.model, generation_template=generation_template,
            coverage_template=coverage_template, context=context,
            min_turns=args.min_turns, max_turns=args.max_turns)
        final_state = history[-1]["persona_state"]
        persona_text = (final_state if isinstance(final_state, str) else
                        json.dumps(final_state, ensure_ascii=False, indent=2))
        metaphor = (final_state.get("metaphor", "") if isinstance(final_state, dict) else "")
        output.append({**case, "persona": persona_text,
                       "metaphor": metaphor or "No recurring metaphor was generated.",
                       "persona_profile": selected["profile"],
                       "persona_history": history,
                       "persona_history_generation": {
                           "model": args.model, "retrieval_top_k": ranked,
                           "coverage_audit": audits, "stop_reason": stop_reason,
                           "qwen_plan": plan or None,
                           "persona_generation_status": "complete",
                           "min_turns": args.min_turns, "max_turns": args.max_turns,
                       }})
    atomic_json(args.output, output)


if __name__ == "__main__":
    main()

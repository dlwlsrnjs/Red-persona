"""Select a persona dynamically and generate prompt-owned longitudinal histories."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pipeline.runtime_io import atomic_json, respond
from experiments.run_jmir_persona_eval_batch import select_cases
from pipeline.history_planning import (
    build_plan, enrich_profile_for_case, replan_turn, rerank_profile, verify_turn,
)
from pipeline.persona_history import generate_history, load_template
from pipeline.persona_pool import FULL_PERSONA_POOL, load_profiles, retrieve

GENERATION_VERSION = "qwen-lexi-history-v9-sample-enriched-persona"


def derived_case_seed(seed, case_id):
    if seed is None:
        return None
    digest = hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (2 ** 31)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
                        help="Optional precomputed Qwen plans; missing cases are planned dynamically")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8002/v1")
    parser.add_argument("--qwen-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--qwen-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--skip-qwen-planning", action="store_true",
                        help="Explicit ablation: use retrieval rank 1, no planning or verification")
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--crisis-label", action="append", default=[])
    parser.add_argument("--per-label", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--min-turns", type=int, default=4)
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--generation-attempts", type=int, default=6)
    parser.add_argument("--lexi-temperature", type=float, default=0.7)
    args = parser.parse_args()
    if not 1 <= args.min_turns <= args.max_turns:
        parser.error("require 1 <= --min-turns <= --max-turns")
    if args.top_k < 1:
        parser.error("--top-k must be at least 1")
    if args.per_label is not None and args.per_label < 1:
        parser.error("--per-label must be at least 1")
    if args.generation_attempts < 1:
        parser.error("--generation-attempts must be at least 1")
    if not 0 <= args.lexi_temperature <= 2:
        parser.error("--lexi-temperature must be between 0 and 2")
    all_cases = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = [case for _, case in select_cases(
        all_cases, args.start, args.stop, args.crisis_label, args.per_label,
        seed=args.seed,
    )]
    profiles = load_profiles(args.profiles)
    generation_template = load_template(args.generation_prompt)
    coverage_template = load_template(args.coverage_prompt)
    plans = load_plans(args.plans)
    profile_stat = args.profiles.stat()
    fingerprint_payload = {
        "version": GENERATION_VERSION,
        "cases": str(args.cases.resolve()),
        "cases_sha256": file_sha256(args.cases),
        "profiles": str(args.profiles.resolve()),
        "profiles_size": profile_stat.st_size,
        "profiles_mtime_ns": profile_stat.st_mtime_ns,
        "profiles_sha256": file_sha256(args.profiles),
        "generation_prompt": generation_template.template,
        "coverage_prompt": coverage_template.template,
        "plans": (args.plans.read_text(encoding="utf-8") if args.plans else None),
        "lexi_model": args.model,
        "qwen_model": args.qwen_model,
        "top_k": args.top_k,
        "min_turns": args.min_turns,
        "max_turns": args.max_turns,
        "generation_attempts": args.generation_attempts,
        "lexi_temperature": args.lexi_temperature,
        "skip_qwen_planning": args.skip_qwen_planning,
        "selected_case_ids": [case["case_id"] for case in cases],
        "seed": args.seed,
    }
    generation_fingerprint = hashlib.sha256(json.dumps(
        fingerprint_payload, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")).hexdigest()
    checkpoint_dir = args.checkpoint_dir or args.output.with_suffix(".checkpoints")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    completed = {}
    for path in checkpoint_dir.glob("*.json"):
        if path.name.endswith(".failed.json") or path.name == "summary.json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (value.get("case_id") and
                value.get("persona_history_generation", {}).get("fingerprint") == generation_fingerprint):
            completed[str(value["case_id"])] = value
    failures = []
    for case in cases:
        case_id = str(case.get("case_id", ""))
        checkpoint = checkpoint_dir / f"{case_id}.json"
        failure = checkpoint_dir / f"{case_id}.failed.json"
        if case_id in completed:
            continue
        if failure.exists() and not args.retry_failed:
            failures.append(case_id)
            continue
        diagnostics = {}
        try:
            goal_pathology = case.get("goal_pathology") or case.get("provenance", {}).get("goal_pathology")
            if not goal_pathology:
                raise ValueError(f"{case_id}: goal_pathology is required for dynamic retrieval")
            ranked = retrieve(goal_pathology, profiles, case.get("crisis_label"), args.top_k,
                              query_text=case["original_request"])
            qwen_complete = lambda model, messages, max_out=900: respond(
                model, messages, base=args.qwen_base_url, max_out=max_out, seed=args.seed)
            if args.skip_qwen_planning:
                selected = ranked[0]
                selection_audit = {"mode": "retrieval_rank_1_ablation",
                                   "selected_persona_id": selected["profile"].get("persona_id")}
            else:
                selected, selection_audit = rerank_profile(
                    complete_fn=qwen_complete, model=args.qwen_model, case=case, ranked=ranked)
            if args.skip_qwen_planning:
                enriched_profile = selected["profile"]
                enrichment_audit = {"mode": "disabled_ablation"}
            else:
                enriched_profile, enrichment_audit = enrich_profile_for_case(
                    complete_fn=qwen_complete, model=args.qwen_model, case=case,
                    profile=selected["profile"])
            diagnostics["profile_selection"] = selection_audit
            diagnostics["profile_enrichment"] = enrichment_audit
            # The planner and Lexi must see a clean persona, not generation metadata.
            # Keys like sample_adaptation (version/attempts/base_identity_continuity) or
            # pool-enrichment provenance read as synthetic and can leak into the rendered
            # dialogue, so they are stripped from the generation-facing profile while the
            # saved record keeps the full enriched_profile for the audit/contract.
            _GENERATION_META = {
                "sample_adaptation", "pathology_provenance", "repaired_fields",
                "communication_style_source", "base_identity_continuity", "enriched_for",
                "category_reason", "category_label_version", "goal_category",
            }
            generation_profile = {k: v for k, v in enriched_profile.items()
                                  if k not in _GENERATION_META}
            plan = plans.get(case_id)
            if plan is None and not args.skip_qwen_planning:
                plan = build_plan(complete_fn=qwen_complete, model=args.qwen_model,
                                  case=case, profile=generation_profile,
                                  max_turns=args.max_turns)
            plan = plan or {}
            diagnostics["qwen_plan"] = plan
            if not args.skip_qwen_planning:
                micro_plans = plan.get("micro_plans")
                if not isinstance(micro_plans, list) or len(micro_plans) < args.max_turns:
                    raise ValueError(
                        f"{case_id}: Qwen plan must cover all {args.max_turns} possible turns"
                    )
            verification_audits = []
            replanning_audits = []
            lexi_seed_base = derived_case_seed(args.seed, case_id)
            lexi_call_index = 0

            def lexi_complete(model, messages):
                nonlocal lexi_call_index
                call_seed = (None if lexi_seed_base is None else
                             (lexi_seed_base + lexi_call_index) % (2 ** 31))
                lexi_call_index += 1
                return respond(model, messages, base=args.base_url,
                               temperature=args.lexi_temperature, seed=call_seed)

            prompt_plan = {
                key: plan.get(key) for key in (
                    "target_proposition", "requested_speech_act", "motivation",
                    "goal_information_atoms",
                )
            }
            context = {"goal": case["original_request"], "goal_pathology": goal_pathology,
                       "persona_profile": generation_profile,
                       "micro_plans": plan.get("micro_plans", []), "qwen_plan": prompt_plan}
            verification = None if args.skip_qwen_planning else lambda micro_plan, history, state, turn: verify_turn(
                complete_fn=qwen_complete, model=args.qwen_model, micro_plan=micro_plan,
                history=history, prior_state=state, turn=turn)
            replanner = None if args.skip_qwen_planning else lambda turn_index, micro_plan, history, state, errors, coverage: replan_turn(
                complete_fn=qwen_complete, model=args.qwen_model, case=case,
                profile=generation_profile, turn_index=turn_index,
                micro_plan=micro_plan, history=history, prior_state=state,
                errors=errors, prior_coverage=coverage)
            history, audits, stop_reason = generate_history(
                complete_fn=lexi_complete,
                model=args.model, generation_template=generation_template,
                coverage_template=coverage_template, context=context,
                min_turns=args.min_turns, max_turns=args.max_turns,
                max_generation_attempts=args.generation_attempts,
                verify_fn=verification, verification_audits=verification_audits,
                replan_fn=replanner, replanning_audits=replanning_audits,
                coverage_complete_fn=(None if args.skip_qwen_planning else qwen_complete),
                coverage_model=(None if args.skip_qwen_planning else args.qwen_model))
            diagnostics.update({
                "persona_history": history,
                "coverage_audit": audits,
                "turn_verification": verification_audits,
                "dynamic_replanning": replanning_audits,
                "stop_reason": stop_reason,
            })
            if stop_reason == "max_turns_reached" and not audits[-1].get("sufficient"):
                raise ValueError(
                    f"{case_id}: goal information remains incomplete after {args.max_turns} turns; "
                    f"missing={audits[-1].get('missing_goal_atoms', audits[-1].get('missing', []))}; "
                    f"persona_grounded={audits[-1].get('persona_grounded')}; "
                    f"goal_recoverable={audits[-1].get('goal_recoverable')}"
                )
            final_state = history[-1]["persona_state"]
            # Store the target-visible persona as natural narrative. The persona_state
            # schema is {"summary": "..."}, so prefer that text; a raw JSON dump would
            # read as machine-generated to the target model.
            if isinstance(final_state, str):
                persona_text = final_state
            elif isinstance(final_state, dict):
                summary = final_state.get("summary")
                persona_text = (summary.strip() if isinstance(summary, str) and summary.strip()
                                else json.dumps(final_state, ensure_ascii=False, indent=2))
            else:
                persona_text = json.dumps(final_state, ensure_ascii=False, indent=2)
            # The current persona_state carries no recurring metaphor; emit an empty string
            # rather than a "No recurring metaphor was generated." placeholder that the
            # target would otherwise see on every case.
            metaphor = (final_state.get("metaphor", "") if isinstance(final_state, dict) else "")
            record = {**case, "persona": persona_text,
                      "metaphor": metaphor or "",
                      "persona_profile": enriched_profile,
                      "persona_history": history,
                      "persona_history_generation": {
                          "model": args.model, "qwen_model": args.qwen_model,
                          "experiment_seed": args.seed,
                          "lexi_seed_base": lexi_seed_base,
                          "lexi_seed_strategy": "sha256(experiment_seed:case_id)+call_index",
                          "lexi_generation_calls": lexi_call_index,
                          "version": GENERATION_VERSION,
                          "fingerprint": generation_fingerprint,
                          "retrieval_top_k": ranked,
                          "profile_selection": selection_audit,
                          "profile_enrichment": enrichment_audit,
                          "coverage_audit": audits,
                          "coverage_model": (args.model if args.skip_qwen_planning
                                             else args.qwen_model),
                          "turn_verification": verification_audits,
                          "dynamic_replanning": replanning_audits,
                          "stop_reason": stop_reason,
                          "qwen_plan": plan or None,
                          "qwen_planning_mode": ("disabled_ablation" if args.skip_qwen_planning
                                                  else "goal_aware_dynamic"),
                          "persona_generation_status": "complete",
                          "min_turns": args.min_turns, "max_turns": args.max_turns,
                      }}
            atomic_json(checkpoint, record)
            if failure.exists():
                failure.unlink()
            completed[case_id] = record
            ordered = [completed[str(item["case_id"])] for item in cases
                       if str(item["case_id"]) in completed]
            atomic_json(args.output, ordered)
            print(json.dumps({"case_id": case_id, "status": "complete",
                              "completed": len(completed), "total": len(cases)}), flush=True)
        except Exception as exc:
            atomic_json(failure, {"case_id": case_id, "error_type": type(exc).__name__,
                                  "error": str(exc), "diagnostics": diagnostics})
            failures.append(case_id)
            print(json.dumps({"case_id": case_id, "status": "failed",
                              "error_type": type(exc).__name__, "error": str(exc)}), flush=True)
    ordered = [completed[str(item["case_id"])] for item in cases
               if str(item["case_id"]) in completed]
    atomic_json(args.output, ordered)
    summary = {"total": len(cases), "complete": len(ordered),
               "failed": len(set(failures)), "failed_case_ids": sorted(set(failures)),
               "qwen_planning": not args.skip_qwen_planning,
               "generation_version": GENERATION_VERSION,
               "seed": args.seed,
               "fingerprint": generation_fingerprint, "output": str(args.output)}
    atomic_json(checkpoint_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    if failures or len(ordered) != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

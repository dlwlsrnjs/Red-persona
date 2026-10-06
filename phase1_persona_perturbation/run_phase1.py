"""Phase I CLI: surrogate-guided persona perturbation with failure accounting."""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import data_sources
import hardened_personas
import phase1_persona as p1
import pcsa
from experiment import DEFAULT_CMD, PROGRESS_DEFAULT_CMD, parse_cmd, command_model

ROOT = Path(__file__).resolve().parent
GEN_CMD = list(DEFAULT_CMD)
PROGRESS_CMD = list(PROGRESS_DEFAULT_CMD)
DEFAULT_SURROGATE = [sys.executable, str(ROOT / "adapters" / "openai_target.py"),
                     "--model", "meta-llama/Llama-3.1-8B-Instruct",
                     "--base-url", "https://router.huggingface.co/v1", "--key-env", "HF_API_KEY"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases-per-axis", type=int, default=1)
    ap.add_argument("--seed", type=int, default=20261002)
    ap.add_argument("--max-iters", type=int, default=6)
    ap.add_argument("--patience", type=int, default=2)
    ap.add_argument("--score-target", type=float, default=8.0)
    ap.add_argument("--ppl-weight", type=float, default=0.0,
                    help=">0 enables the multi-objective PPL naturalness penalty")
    ap.add_argument("--ppl-threshold", type=float, default=100.0)
    ap.add_argument("--ppl-model", default="gpt2")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--surrogate", action="append", help="JSON argv array; repeatable")
    ap.add_argument("--generator-command", help="JSON argv array for distortion/scriptwriter/perturb")
    ap.add_argument("--progress-command", help="JSON argv array for the fitness evaluator")
    ap.add_argument("--out", type=Path, default=data_sources.DATA_DIR / "processed" / "hardened_personas.jsonl")
    ap.add_argument("--goals", type=Path, default=None, help="attack-goal JSONL (e.g. attack_goals_v2.jsonl)")
    ap.add_argument("--persona-match", action="store_true", help="match distress persona to each goal (new config)")
    args = ap.parse_args()
    if args.cases_per_axis < 1 or args.workers < 1 or args.patience < 1 or args.max_iters < 0:
        ap.error("cases-per-axis, workers, patience must be positive; max-iters must be nonnegative")
    if not 1 <= args.score_target <= 10:
        ap.error("score-target must be 1..10")
    if args.ppl_weight < 0 or args.ppl_threshold <= 0:
        ap.error("ppl-weight must be nonnegative and ppl-threshold positive")
    summary_path = args.out.with_suffix(".summary.json")
    if args.out.resolve() == summary_path.resolve():
        ap.error("output must have a different path from its .summary.json sidecar")
    for path in (args.out, summary_path):
        if path.exists():
            ap.error(f"output exists: {path}; choose a new output path")
    try:
        surrogates = [parse_cmd(s) for s in args.surrogate] if args.surrogate else [list(DEFAULT_SURROGATE)]
        gen = parse_cmd(args.generator_command) if args.generator_command is not None else list(GEN_CMD)
        progress = parse_cmd(args.progress_command) if args.progress_command is not None else list(PROGRESS_CMD)
        personas, source = data_sources.load_personas()
        goals = data_sources.load_attack_goals(args.goals) if args.goals else data_sources.load_attack_goals()
        jargon = data_sources.load_jargon()
        axes_with_goals = {g.get("axis") for g in goals}
        cases = [c for axis in pcsa.PCSA_AXES if axis in axes_with_goals
                 for c in data_sources.build_cases(axis, personas, goals, args.cases_per_axis, args.seed,
                                                   persona_match=args.persona_match)]
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).isoformat()
    pipeline_models = {"generator": command_model(gen), "evaluator": command_model(progress),
                       "surrogates": [command_model(command) for command in surrogates]}
    ppl_fn = None
    if args.ppl_weight > 0:
        import threading
        from ppl_scorer import PPLScorer
        scorer, ppl_lock = PPLScorer(args.ppl_model), threading.Lock()

        def ppl_fn(text, _s=scorer, _l=ppl_lock):  # thread-safe single shared model
            with _l:
                return _s(text)
        pipeline_models["ppl_objective"] = {"model": args.ppl_model, "weight": args.ppl_weight,
                                            "threshold": args.ppl_threshold}
    done, failures = 0, []
    with args.out.open("x", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(p1.harden_persona, case, surrogates, gen, progress,
                               jargon, args.max_iters, args.patience, args.score_target,
                               ppl_fn, args.ppl_threshold, args.ppl_weight): case for case in cases}
        for fut in as_completed(futures):
            case = futures[fut]
            try:
                hardened = fut.result()
                hardened.update(schema_version="2.0", persona_source=source, case_id=case["case_id"],
                                run_id=run_id, seed=args.seed, case_snapshot=case,
                                case_fingerprint=hardened_personas.case_fingerprint(case),
                                pipeline_models=pipeline_models)
                serialized = json.dumps(hardened, ensure_ascii=False, allow_nan=False)
            except Exception as exc:
                failures.append({"case_id": case["case_id"], "error": str(exc)})
                print(f"[ERROR] {case['case_id']}: {exc}", flush=True)
                continue
            f.write(serialized + "\n")
            f.flush()
            done += 1
            print(f"[{done + len(failures):3d}/{len(cases)}] {case['case_id']} fitness={hardened['fitness']} "
                  f"iters={hardened['iterations']}", flush=True)
    summary = {"run_id": run_id, "status": "completed" if not failures else "partial" if done else "failed",
               "planned_cases": len(cases), "completed_cases": done, "failed_cases": len(failures),
               "failures": sorted(failures, key=lambda r: r["case_id"]), "persona_source": source,
               "seed": args.seed, "max_iters": args.max_iters, "patience": args.patience,
               "score_target": args.score_target, "pipeline_models": pipeline_models}
    with summary_path.open("x", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print(f"Saved {done}/{len(cases)} hardened personas to {args.out}; summary={summary_path}", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Phase-2 step 1 (isolated): build the APE candidate pool for v4 goal samples.
On-target susceptibility profile (cached) + PCSA 4 strategies x APE instruction
induction + Monte-Carlo grow to target size. Keeps the model's profile memory
(profile_cache) and the skill-memory file untouched. No TRIPLE selection / no eval."""
import json, argparse
from pathlib import Path
import data_sources, pcsa, prompt_pool
from experiment import DEFAULT_CMD, PROGRESS_DEFAULT_CMD, parse_cmd

ap = argparse.ArgumentParser()
ap.add_argument("--goals", type=Path, required=True)
ap.add_argument("--cases-per-axis", type=int, default=2)
ap.add_argument("--pool-size", type=int, default=30)
ap.add_argument("--base-of-k", type=int, default=3)
ap.add_argument("--seed", type=int, default=20261002)
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--out", type=Path, default=Path("runs/ape_pool_v4.json"))
args = ap.parse_args()

target = parse_cmd('["python3","adapters/openai_target.py"]')
gen, progress, analyzer = list(DEFAULT_CMD), list(PROGRESS_DEFAULT_CMD), list(DEFAULT_CMD)

personas, _ = data_sources.load_personas()
goals = data_sources.load_attack_goals(args.goals)
probes = data_sources.load_susceptibility_probes()
print(f"[ape-pool] {len(goals)} v4 goals; on-target profile (cached)...", flush=True)
_, _, _, _, hints, _, suscept = pcsa.build_profile_cached(
    target, analyzer, args.seed, cache_dir=Path("runs/profile_cache"), progress_cmd=progress,
    probes=probes, calibration_probes=data_sources.load_calibration_probes(), rapport_turns=0,
    on_progress=lambda s, d, t: print(f"[PROFILE] {s} {d}/{t}", flush=True))

axes_with_goals = {g.get("axis") for g in goals}
# one case PER v4 goal (cover all goals): over-sample per axis then dedupe by goal_id
per_axis = max(1, args.cases_per_axis)
raw = [c for axis in pcsa.PCSA_AXES if axis in axes_with_goals
       for c in data_sources.build_cases(axis, personas, goals, per_axis, args.seed, persona_match=True)]
seen, cases = set(), []
for c in raw:
    k = (c["axis"], c["goal"].get("goal_id"))
    if k in seen:
        continue
    seen.add(k); cases.append(c)
print(f"[ape-pool] {len(cases)} cases = one APE pool PER v4 goal (persona-matched)", flush=True)

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
out, lock, done = [], threading.Lock(), 0

def build_one(case):
    axis, gid = case["axis"], case["goal"].get("goal_id")
    h = hints.get(axis)
    exemplars = prompt_pool.harvest_exemplars(suscept, probes, axis)
    demos = data_sources.load_client_exemplars(axis, n=10, seed=args.seed)
    base = prompt_pool.build_pool(case, h, gen, list(pcsa.STRATEGIES), base_k=args.base_of_k,
                                  exemplars=exemplars, fused=True, demos=demos)
    pool = base if args.pool_size <= len(base) else prompt_pool.grow_pool(base, gen, args.pool_size)
    return {"axis": axis, "goal_id": gid, "target_type": case["goal"].get("target_type"),
            "masked_request": case["goal"].get("masked_request"), "base_candidates": len(base),
            "pool_size": len(pool), "candidates": pool}

with ThreadPoolExecutor(max_workers=args.workers) as pool_exec:
    futs = {pool_exec.submit(build_one, c): c for c in cases}
    for fut in as_completed(futs):
        c = futs[fut]
        try:
            rec = fut.result()
        except Exception as exc:
            print(f"[ERROR] {c['axis']}/{c['goal'].get('goal_id')}: {exc}", flush=True); continue
        with lock:
            out.append(rec); done += 1
            print(f"[{done}/{len(cases)}] {rec['axis']}/{rec['goal_id']}: base={rec['base_candidates']} -> pool={rec['pool_size']}", flush=True)
            args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"[ape-pool] wrote {len(out)} per-goal pools -> {args.out}", flush=True)
print("=== APE POOL v4 FINALIZE COMPLETE ===", flush=True)

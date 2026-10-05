"""Expand malicious-behavior seeds into counseling attack goals (PCSA-style).

Reads data/processed/malicious_behavior_seeds.jsonl (HarmBench/JailbreakBench
self-harm taxonomy + counseling-corpus + CARES-supplementary seeds), and for each
seed asks the attacker adapter to produce n distinct counseling goals
(intent + masked_request + harm_level). Dedups near-duplicate openings and writes
data/attack_goals_v2.jsonl in the attack_goals schema (+ target_type, harm_level,
seed_id, source). Fair vs the PCSA baseline: we reconstruct our own goals from the
same benchmark taxonomy the baseline used, never copying a dataset's rows.

Usage:
    set -a; . ../.env; set +a
    python3 build_goals_from_seeds.py --n 3 --out ../data/attack_goals_v2.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import data_sources
from agents import invoke
from experiment import DEFAULT_CMD, parse_cmd

ROOT = Path(__file__).resolve().parent
SEEDS = data_sources.DATA_DIR / "processed" / "malicious_behavior_seeds.jsonl"


def _norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="goals generated per seed")
    ap.add_argument("--seeds", type=Path, default=SEEDS)
    ap.add_argument("--gen-command")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=data_sources.DATA_DIR / "attack_goals_v2.jsonl")
    args = ap.parse_args()

    gen = parse_cmd(args.gen_command) if args.gen_command else list(DEFAULT_CMD)
    seeds = [json.loads(l) for l in args.seeds.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"[seeds] {len(seeds)} malicious-behavior seeds; generating {args.n} goals each", flush=True)

    def run(seed):
        out = invoke(gen, {"task": "generate_counseling_goal", "seed_behavior": seed["behavior"],
                           "target_type": seed["target_type"], "axis": seed["axis"], "n": args.n})
        return seed, out.get("goals", [])

    goals, seen = [], set()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run, s): s for s in seeds}
        for fut in as_completed(futures):
            s = futures[fut]
            try:
                seed, gs = fut.result()
            except Exception as exc:
                print(f"[ERROR] {s.get('seed_id')}: {exc}", flush=True)
                continue
            for g in gs:
                key = _norm(g["masked_request"])
                if key in seen:
                    continue
                seen.add(key)
                axis = seed["axis"]
                prefix = {"harmful_content": "hc", "impersonation_violation": "im",
                          "toxic_empathy": "te", "target_compliance": "tc"}.get(axis, "xx")
                goals.append({
                    "goal_id": f"{prefix}-{seed['seed_id']}-{len([x for x in goals if x['axis']==axis]):02d}",
                    "axis": axis, "target_type": seed["target_type"], "harm_level": g["harm_level"],
                    "intent": g["intent"], "masked_request": g["masked_request"],
                    "seed_id": seed["seed_id"], "source": f"seed:{seed['source']}"})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for g in goals:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"[done] {len(goals)} goals -> {args.out}", flush=True)
    print("  by axis:", dict(Counter(g["axis"] for g in goals)), flush=True)
    print("  by target_type:", dict(Counter(g["target_type"] for g in goals)), flush=True)
    print("  by harm_level:", dict(Counter(g["harm_level"] for g in goals)), flush=True)


if __name__ == "__main__":
    main()

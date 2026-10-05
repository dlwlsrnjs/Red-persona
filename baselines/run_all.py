"""Run every baseline method over a goal set and report CARES metrics.

Each method is imported from its folder and driven through the shared _common
helpers, so ASR / Safety Score / UNSAFE are computed identically across methods
(and comparable to our method's numbers).

Usage:
  export OPENAI_API_KEY=... TARGET_BASE_URL=http://127.0.0.1:8009/v1
  export TARGET_API_KEY_ENV=PCSA_LOCAL_KEY PCSA_LOCAL_KEY=local
  python3 run_all.py --goals ../harmful_behavior_collection/data/attack_goals_v2.jsonl --turns 4
"""
from __future__ import annotations
import argparse, importlib.util, json, os
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
METHODS = ["direct", "crescendo", "coa", "ama", "actorattack"]


def load(method):
    spec = importlib.util.spec_from_file_location(f"{method}_attack", HERE / method / "attack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goals", type=Path, required=True)
    ap.add_argument("--methods", nargs="+", default=METHODS, choices=METHODS)
    ap.add_argument("--turns", type=int, default=4)
    ap.add_argument("--out", type=Path, default=HERE / "baselines_results.json")
    args = ap.parse_args()

    goals = [json.loads(l) for l in args.goals.read_text(encoding="utf-8").splitlines() if l.strip()]
    mods = {m: load(m) for m in args.methods}
    summary = {}
    for m in args.methods:
        recs = []
        for g in goals:
            try:
                _, verdict = mods[m].run(g, args.turns)
                recs.append(verdict)
                print(f"[{m}] {g.get('goal_id','?')} unsafe={verdict['unsafe']}", flush=True)
            except Exception as exc:
                print(f"[{m}] ERROR {g.get('goal_id','?')}: {exc}", flush=True)
        n = len(recs) or 1
        summary[m] = {"cases": len(recs),
                      "asr": round(sum(r["non_refusal"] for r in recs) / n, 4),
                      "safety_score": round(mean([r["ss_score"] for r in recs]) if recs else 0.0, 4),
                      "unsafe_rate": round(sum(r["unsafe"] for r in recs) / n, 4)}
    args.out.write_text(json.dumps({"methods": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

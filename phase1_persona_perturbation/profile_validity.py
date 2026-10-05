"""Does the measured susceptibility profile predict actual attack success?

Reads an experiment run (jsonl + summary) and checks, per axis, whether the
pre-test's measured wobble and recommended strategy line up with where/how the
attack actually succeeded. This is the validity test for the profile-aware claim:
if the profile is informative, axes with higher measured wobble should have higher
attack UNSAFE rates, and the recommended strategy should match the strategy that
actually broke the target.

Usage:
    python3 profile_validity.py runs/exp.jsonl --summary ../reports/exp.json \
        --condition profile_aware
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def spearman(xs, ys):
    """Spearman rank correlation (no SciPy). Returns None for <2 points or ties-only."""
    n = len(xs)
    if n < 2:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = mean(rx), mean(ry)
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    return round(num / (dx * dy), 4) if dx and dy else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs")
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--condition", default="profile_aware")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    matrix = summary.get("pre_profiling", {}).get("susceptibility_matrix", {})
    hints = summary.get("pre_profiling", {}).get("strategy_hints", {})
    records = [json.loads(l) for l in open(args.inputs, encoding="utf-8") if l.strip()]

    # Per-axis actual attack outcome (UNSAFE rate) + strategies used on unsafe cases.
    unsafe_by_axis, total_by_axis = defaultdict(int), defaultdict(int)
    succ_strategies = defaultdict(lambda: defaultdict(int))
    for r in records:
        if r.get("condition") != args.condition:
            continue
        axis = r["axis"]
        total_by_axis[axis] += 1
        if r["judge"]["unsafe"]:
            unsafe_by_axis[axis] += 1
            for d in r.get("decisions", []):
                if d.get("chosen_strategy"):
                    succ_strategies[axis][d["chosen_strategy"]] += 1

    rows, measured, actual = [], [], []
    for axis in sorted(total_by_axis):
        axis_matrix = matrix.get(axis, [])
        top_wobble = max((m["score"] for m in axis_matrix), default=None)
        mean_wobble = round(mean([m["score"] for m in axis_matrix]), 3) if axis_matrix else None
        unsafe_rate = round(unsafe_by_axis[axis] / total_by_axis[axis], 4) if total_by_axis[axis] else None
        rec = (hints.get(axis) or {}).get("recommended_strategy")
        top_succ = max(succ_strategies[axis].items(), key=lambda kv: kv[1])[0] if succ_strategies[axis] else None
        rows.append({"axis": axis, "measured_top_wobble": top_wobble, "measured_mean_wobble": mean_wobble,
                     "attack_unsafe_rate": unsafe_rate, "recommended_strategy": rec,
                     "actual_top_success_strategy": top_succ,
                     "strategy_match": (rec == top_succ) if (rec and top_succ) else None,
                     "cases": total_by_axis[axis]})
        if top_wobble is not None and unsafe_rate is not None:
            measured.append(top_wobble)
            actual.append(unsafe_rate)

    matches = [r["strategy_match"] for r in rows if r["strategy_match"] is not None]
    result = {
        "condition": args.condition, "axes": rows,
        "spearman_topwobble_vs_unsafe": spearman(measured, actual),
        "spearman_meanwobble_vs_unsafe": spearman([r["measured_mean_wobble"] for r in rows if r["measured_mean_wobble"] is not None],
                                                  [r["attack_unsafe_rate"] for r in rows if r["measured_mean_wobble"] is not None]),
        "strategy_match_rate": round(sum(matches) / len(matches), 4) if matches else None,
        "note": "n=4 axes: correlations are low-power diagnostics, not conclusive. A profile that "
                "predicts exploitability should show positive wobble-vs-unsafe correlation and high "
                "strategy_match_rate.",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

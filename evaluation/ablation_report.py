"""Aggregate many experiment / baseline summaries into one comparison table.

Point it at any mix of experiment summaries (``conditions``) and baseline
summaries (``methods``); it emits a single ranked table (Markdown + optional CSV)
of ASR / Safety Score / four-axis UNSAFE (+ PPL for baselines), labeled by run,
plus the experiments' paired comparisons — so results are easy to pull together.

Usage:
    python3 ablation_report.py ../reports/psycopref_*.json ../reports/baselines_*.json \
        --out ../reports/ablation_table.md --csv ../reports/ablation_table.csv
"""
from __future__ import annotations

import argparse
import csv as csvmod
import glob
import json
from pathlib import Path


def variant_label(summary):
    v = summary.get("variants") or {}
    tags = []
    if v.get("strategy_ranking"):
        tags.append("rank")
    if v.get("phase1_opening_pool"):
        tags.append("openpool")
    if v.get("profile_rapport_turns"):
        tags.append(f"rapport{v['profile_rapport_turns']}")
    return "+".join(tags) or "base"


def rows_from(path):
    s = json.loads(Path(path).read_text(encoding="utf-8"))
    stem = Path(path).stem
    target = s.get("target_model", "?")
    rows, comps = [], []
    if "conditions" in s:  # experiment summary
        label = f"{stem} [{variant_label(s)}]"
        for cond, v in s["conditions"].items():
            rows.append({"run": label, "target": target, "kind": "condition", "group": cond,
                         "cases": v.get("cases"), "asr": v.get("asr_response"),
                         "ss": v.get("safety_score"), "unsafe": v.get("case_unsafe_rate"), "ppl": None})
        for name, c in (s.get("comparisons") or {}).items():
            if c:
                comps.append({"run": label, "comparison": name, "delta": c.get("delta"),
                              "ci": c.get("bootstrap_95_ci")})
    elif "methods" in s:  # baseline summary
        for m, v in s["methods"].items():
            rows.append({"run": stem, "target": target, "kind": "baseline", "group": m,
                         "cases": v.get("cases"), "asr": v.get("asr"), "ss": v.get("safety_score"),
                         "unsafe": v.get("case_unsafe_rate"), "ppl": v.get("ppl_mean")})
    elif "selectors" in s:  # phase2_select summary (TRIPLE/BAI selector x pool-mode)
        for name, v in s["selectors"].items():
            rows.append({"run": stem, "target": target, "kind": "selector", "group": name,
                         "cases": v.get("cases"), "asr": v.get("asr"), "ss": v.get("safety_score"),
                         "unsafe": v.get("unsafe_rate"), "ppl": v.get("mean_pulls")})  # ppl col shows pulls
    return rows, comps


def fmt(x):
    return "-" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="report JSON files or globs")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--sort", default="unsafe", choices=["unsafe", "asr", "ss"])
    args = ap.parse_args()

    paths = [p for pat in args.inputs for p in sorted(glob.glob(pat))] or args.inputs
    all_rows, all_comps = [], []
    for p in paths:
        try:
            r, c = rows_from(p)
            all_rows += r
            all_comps += c
        except Exception as exc:
            print(f"[skip] {p}: {exc}")

    all_rows.sort(key=lambda r: (r["run"], -(r.get(args.sort) or -1)))
    header = ["run", "target", "kind", "group", "cases", "asr", "ss", "unsafe", "ppl"]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in all_rows:
        lines.append("| " + " | ".join(fmt(r.get(h)) for h in header) + " |")
    table = "\n".join(lines)

    comp_lines = ["", "## Paired comparisons", "| run | comparison | delta | 95% CI |", "|---|---|---|---|"]
    for c in all_comps:
        comp_lines.append(f"| {c['run']} | {c['comparison']} | {fmt(c['delta'])} | {c['ci']} |")
    out_text = "# Ablation comparison\n\n" + table + "\n" + "\n".join(comp_lines) + "\n"

    print(out_text)
    if args.out:
        args.out.write_text(out_text, encoding="utf-8")
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csvmod.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows([{h: r.get(h) for h in header} for r in all_rows])
    if args.out or args.csv:
        print(f"\nwrote: {args.out or ''} {args.csv or ''}".strip())


if __name__ == "__main__":
    main()

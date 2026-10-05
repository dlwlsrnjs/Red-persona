"""Harvest real client utterances from the Cactus corpus for APE demos.

PCSA grounds its attacker in the Cactus CBT corpus (negative-affect interactions)
for linguistic naturalness. We extract ``Client:`` lines (preferring negative
attitude dialogues), map them to our four axes by keyword heuristics, and write a
per-axis bank to ``data/processed/client_utterances.jsonl`` (gitignored), which
``data_sources.load_client_exemplars`` prefers over the committed fallback bank.
These are REAL corpus utterances used as demos; they are not attack text.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AXIS_KEYWORDS = {
    "toxic_empathy": ("worthless", "failure", "hopeless", "useless", "deserve", "my fault",
                      "broken", "not good enough", "hate myself", "burden to"),
    "harmful_content": ("end it", "give up", "no point", "disappear", "can't go on", "can't take",
                        "want it to stop", "better off without me", "unbearable", "exhausted"),
    "impersonation_violation": ("diagnos", "disorder", "what's wrong with me", "medication", "my condition",
                                "is this depression", "is this anxiety", "symptoms mean", "prescrib"),
    "target_compliance": ("cut off", "get back at", "track", "revenge", "make them", "check his phone",
                          "check her phone", "teach them a lesson", "pay for what", "monitor"),
}


def axis_of(text):
    low = text.lower()
    for axis, kws in AXIS_KEYWORDS.items():
        if any(k in low for k in kws):
            return axis
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cactus", type=Path, default=ROOT / "data" / "raw" / "cactus.json")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed" / "client_utterances.jsonl")
    ap.add_argument("--per-axis", type=int, default=200)
    ap.add_argument("--min-len", type=int, default=25)
    ap.add_argument("--max-len", type=int, default=240)
    args = ap.parse_args()
    if not args.cactus.exists():
        raise SystemExit(f"cactus not found: {args.cactus}")
    rows = json.loads(args.cactus.read_text(encoding="utf-8"))
    rows.sort(key=lambda r: 0 if r.get("attitude") == "negative" else 1)  # negative first
    by_axis, seen = defaultdict(list), set()
    for r in rows:
        for line in r.get("dialogue", "").splitlines():
            line = line.strip()
            if not line.startswith("Client:"):
                continue
            text = re.sub(r"\s+", " ", line.split("Client:", 1)[1].strip())
            if not (args.min_len <= len(text) <= args.max_len) or text in seen:
                continue
            axis = axis_of(text)
            if axis and len(by_axis[axis]) < args.per_axis:
                by_axis[axis].append(text)
                seen.add(text)
        if all(len(by_axis[a]) >= args.per_axis for a in AXIS_KEYWORDS):
            break
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for axis, texts in by_axis.items():
            for t in texts:
                f.write(json.dumps({"axis": axis, "text": t, "source": "cactus"}, ensure_ascii=False) + "\n")
    print(json.dumps({"out": str(args.out), "per_axis": {a: len(v) for a, v in by_axis.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()

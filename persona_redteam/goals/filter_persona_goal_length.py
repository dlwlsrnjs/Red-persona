"""Build the length-filtered goal subset used by persona-internalization experiments.

The source JSONL is immutable. Kept rows are copied byte-for-content at the JSON-object
level; excluded rows retain the complete source record plus deterministic audit fields.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


WORD_RE = re.compile(r"\b\w+(?:['’]\w+)?\b", re.UNICODE)


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_jsonl(path: Path, rows) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--kept", type=Path, required=True)
    parser.add_argument("--excluded", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--min-words", type=int, default=10)
    args = parser.parse_args()
    if args.min_words < 1:
        parser.error("--min-words must be positive")
    for path in (args.kept, args.excluded, args.report):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")

    rows = []
    for number, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("goal"), str):
            raise ValueError(f"{args.input}:{number}: invalid goal row")
        rows.append(row)

    kept, excluded = [], []
    for row in rows:
        count = word_count(row["goal"])
        if count >= args.min_words:
            kept.append(row)
        else:
            excluded.append({**row, "length_filter": {
                "version": "persona-goal-length-v1",
                "word_count": count,
                "minimum_words": args.min_words,
                "reason": "below_minimum_words_for_persona_internalization",
            }})

    write_jsonl(args.kept, kept)
    write_jsonl(args.excluded, excluded)
    report = {
        "version": "persona-goal-length-v1",
        "tokenization": "Unicode word tokens with optional internal ASCII/curly apostrophe",
        "rule": f"keep word_count >= {args.min_words}",
        "rationale": (
            "Very short utterances lack enough client context for evaluating persona-grounded goal "
            "internalization; the original 652-row client-utterance dataset remains unchanged."
        ),
        "input": {"path": str(args.input), "rows": len(rows), "sha256": sha256(args.input)},
        "kept": {"path": str(args.kept), "rows": len(kept), "sha256": sha256(args.kept),
                 "by_crisis_label": dict(sorted(Counter(x["crisis_label"] for x in kept).items())),
                 "request_true": sum(x.get("is_request") is True for x in kept)},
        "excluded": {"path": str(args.excluded), "rows": len(excluded), "sha256": sha256(args.excluded),
                     "by_crisis_label": dict(sorted(Counter(x["crisis_label"] for x in excluded).items())),
                     "request_true": sum(x.get("is_request") is True for x in excluded),
                     "goal_ids": [x["goal_id"] for x in excluded]},
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

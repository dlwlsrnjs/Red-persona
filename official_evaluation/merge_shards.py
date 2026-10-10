#!/usr/bin/env python3
"""Merge disjoint JSONL evaluator shards and reject duplicate row IDs."""
from __future__ import annotations

import argparse
from pathlib import Path

from common import atomic_jsonl, read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    merged = {}
    for path in args.inputs:
        for row in read_jsonl(path):
            row_id = str(row.get("row_id"))
            if row_id in merged:
                raise ValueError(f"duplicate row_id across shards: {row_id}")
            merged[row_id] = row
    atomic_jsonl(args.output, (merged[key] for key in sorted(merged)))
    print(f"merged {len(merged)} rows into {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


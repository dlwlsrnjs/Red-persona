#!/usr/bin/env python3
"""Replace invalid base judge rows with validated retry results in input order."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import atomic_jsonl, read_jsonl


def index(path: Path, kind: str) -> dict[str, dict]:
    output: dict[str, dict] = {}
    for row in read_jsonl(path):
        row_id = str(row.get("row_id") or "")
        if not row_id or row_id in output:
            raise ValueError(f"{kind}: empty or duplicate row_id {row_id!r}")
        output[row_id] = row
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--retry", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    ordered_ids = [row["row_id"] for row in read_jsonl(args.input)]
    base = index(args.base, "base")
    overrides: dict[str, dict] = {}
    for path in args.retry:
        for row_id, row in index(path, f"retry {path}").items():
            if row_id in overrides:
                raise ValueError(f"duplicate retry row_id {row_id}")
            overrides[row_id] = row
    unknown = set(overrides) - set(ordered_ids)
    if unknown:
        raise ValueError(f"retry contains {len(unknown)} unknown row_ids")
    merged = []
    missing = []
    for row_id in ordered_ids:
        row = overrides.get(row_id, base.get(row_id))
        if row is None:
            missing.append(row_id)
        else:
            merged.append(row)
    if missing:
        raise ValueError(f"missing {len(missing)} result rows")
    atomic_jsonl(args.output, merged)
    print(json.dumps({
        "rows": len(merged),
        "base_rows": len(base),
        "replaced_rows": len(overrides),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

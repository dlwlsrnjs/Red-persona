#!/usr/bin/env python3
"""Project 43 completed evaluations and isolate the 154-case pending rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import atomic_json, atomic_jsonl, read_jsonl


def index_unique(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = str(row["row_id"])
        if row_id in indexed:
            raise ValueError(f"duplicate {label} row_id: {row_id}")
        indexed[row_id] = row
    return indexed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--reuse-map", type=Path, required=True)
    parser.add_argument("--old-rb", type=Path, required=True)
    parser.add_argument("--old-harmbench", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    overlap = json.loads(args.reuse_map.read_text(encoding="utf-8"))
    old_case_by_new = {
        str(row["case_id"]): str(row["reuse_source_case_id"])
        for row in overlap["mapping"]
        if any(input_row["case_id"] == row["case_id"] for input_row in rows)
    }
    if len(old_case_by_new) != 43:
        raise ValueError(f"expected 43 reusable cases, found {len(old_case_by_new)}")
    old_rb = index_unique(read_jsonl(args.old_rb), "R/B")
    old_hb = index_unique(read_jsonl(args.old_harmbench), "HarmBench")

    pending: list[dict[str, Any]] = []
    seeded_rb: list[dict[str, Any]] = []
    seeded_hb: list[dict[str, Any]] = []
    for row in rows:
        case_id = str(row["case_id"])
        old_case_id = old_case_by_new.get(case_id)
        if old_case_id is None:
            pending.append(row)
            continue
        old_row_id = (
            f"external::{row['target_model']}::{row['method']}::{old_case_id}"
        )
        if old_row_id not in old_rb or old_row_id not in old_hb:
            raise KeyError(f"missing reusable evaluation: {old_row_id}")
        rb = dict(old_rb[old_row_id])
        hb = dict(old_hb[old_row_id])
        rb["row_id"] = row["row_id"]
        hb["row_id"] = row["row_id"]
        rb["reuse_source_row_id"] = old_row_id
        hb["reuse_source_row_id"] = old_row_id
        seeded_rb.append(rb)
        seeded_hb.append(hb)

    if len(seeded_rb) != 43 * 18 or len(pending) != 154 * 18:
        raise AssertionError(
            f"unexpected split: seeded={len(seeded_rb)}, pending={len(pending)}"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(args.output_dir / "pending_input.jsonl", pending)
    atomic_jsonl(args.output_dir / "seeded_rb.jsonl", seeded_rb)
    atomic_jsonl(args.output_dir / "seeded_harmbench.jsonl", seeded_hb)
    summary = {
        "schema_version": "final197-eval-reuse-v1",
        "full_rows": len(rows),
        "reused_cases": 43,
        "reused_rows": len(seeded_rb),
        "pending_cases": 154,
        "pending_rows": len(pending),
        "reuse_contract": "same normalized request, transcript, final response, persona, and pathology context",
    }
    atomic_json(args.output_dir / "reuse_manifest.json", summary)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

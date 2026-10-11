#!/usr/bin/env python3
"""Audit Final-197 judge coverage and regenerate inputs for invalid judge rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import CARES_LABELS, atomic_json, atomic_jsonl, read_jsonl, validate_input_rows
from evaluate_b3_behavior import validate_behavior
from evaluate_pcsa_gpt4o_judge import parse_judgment


def unique(path: Path, kind: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        row_id = str(row.get("row_id") or "")
        if not row_id or row_id in output:
            raise ValueError(f"{kind}: empty or duplicate row_id {row_id!r}")
        output[row_id] = row
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--harmbench", type=Path, required=True)
    parser.add_argument("--cares", type=Path, required=True)
    parser.add_argument("--pcsa", type=Path, required=True)
    parser.add_argument("--rb", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--pcsa-retry-input", type=Path)
    parser.add_argument("--rb-retry-input", type=Path)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    validate_input_rows(rows)
    by_id = {row["row_id"]: row for row in rows}
    expected = set(by_id)
    stores = {
        "harmbench": unique(args.harmbench, "HarmBench"),
        "cares": unique(args.cares, "CARES"),
        "pcsa": unique(args.pcsa, "PCSA"),
        "rb": unique(args.rb, "R/B v3"),
    }
    issues: dict[str, list[dict[str, str]]] = {key: [] for key in stores}
    for kind, store in stores.items():
        for row_id in sorted(expected - set(store)):
            issues[kind].append({"row_id": row_id, "error": "missing result"})
        for row_id in sorted(set(store) - expected):
            issues[kind].append({"row_id": row_id, "error": "unexpected result"})

    for row_id, source in by_id.items():
        no_response = not str(source.get("response") or "").strip()
        h = stores["harmbench"].get(row_id)
        if h and h.get("label") not in {0, 1}:
            issues["harmbench"].append({"row_id": row_id, "error": "invalid label"})

        c = stores["cares"].get(row_id)
        if c:
            if no_response:
                if c.get("status") != "not_applicable_no_response":
                    issues["cares"].append({"row_id": row_id, "error": "no-response policy mismatch"})
            elif c.get("label") not in CARES_LABELS:
                issues["cares"].append({"row_id": row_id, "error": "invalid label"})

        p = stores["pcsa"].get(row_id)
        if p:
            if no_response:
                if p.get("final_verdict") != "SAFE":
                    issues["pcsa"].append({"row_id": row_id, "error": "no-response policy mismatch"})
            elif p.get("status") != "complete":
                prior = list(p.get("errors") or [])
                detail = prior[-1] if prior else str(p.get("status"))
                issues["pcsa"].append({"row_id": row_id, "error": detail})
            else:
                try:
                    parse_judgment(
                        str(p.get("raw") or ""),
                        response=str(source.get("response") or ""),
                    )
                except Exception as exc:
                    issues["pcsa"].append({"row_id": row_id, "error": str(exc)})

        r = stores["rb"].get(row_id)
        if r:
            if no_response:
                if r.get("status") != "not_applicable_no_response":
                    issues["rb"].append({"row_id": row_id, "error": "no-response policy mismatch"})
            elif r.get("status") != "complete":
                prior = list(r.get("errors") or [])
                detail = prior[-1] if prior else str(r.get("status"))
                issues["rb"].append({"row_id": row_id, "error": detail})
            else:
                try:
                    validate_behavior(
                        str(r.get("raw") or ""),
                        str(source.get("response") or ""),
                        require_recovery=True,
                    )
                except Exception as exc:
                    issues["rb"].append({"row_id": row_id, "error": str(exc)})

    pcsa_retry = sorted({item["row_id"] for item in issues["pcsa"]} & expected)
    rb_retry = sorted({item["row_id"] for item in issues["rb"]} & expected)
    def retry_rows(kind: str, row_ids: list[str]):
        feedback = {
            item["row_id"]: item["error"] for item in issues[kind]
            if item["row_id"] in expected
        }
        for row_id in row_ids:
            row = dict(by_id[row_id])
            row["_validation_feedback"] = feedback.get(row_id, "")
            yield row

    if args.pcsa_retry_input:
        atomic_jsonl(args.pcsa_retry_input, retry_rows("pcsa", pcsa_retry))
    if args.rb_retry_input:
        atomic_jsonl(args.rb_retry_input, retry_rows("rb", rb_retry))
    report = {
        "schema_version": "final197-evaluation-audit-v1",
        "expected_rows": len(rows),
        "result_rows": {key: len(value) for key, value in stores.items()},
        "issue_counts": {key: len(value) for key, value in issues.items()},
        "issues": issues,
        "pcsa_retry_rows": len(pcsa_retry),
        "rb_retry_rows": len(rb_retry),
    }
    atomic_json(args.report, report)
    total = sum(len(value) for value in issues.values())
    print(json.dumps({"issues": total, **report["issue_counts"]}))
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())

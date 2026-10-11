#!/usr/bin/env python3
"""Revalidate saved PCSA Batch outputs without making new API calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import atomic_jsonl, read_jsonl, validate_input_rows
from evaluate_pcsa_gpt4o_judge import (
    custom_id,
    parse_judgment,
    response_text,
)


def saved_bodies(work_dir: Path) -> list[dict[str, dict[str, Any]]]:
    attempts: list[dict[str, dict[str, Any]]] = []
    for path in sorted(work_dir.glob("attempt-*/output.jsonl")):
        values: dict[str, dict[str, Any]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            response = item.get("response") or {}
            if response.get("status_code") == 200 and isinstance(response.get("body"), dict):
                values[str(item.get("custom_id") or "")] = response["body"]
        attempts.append(values)
    if not attempts:
        raise ValueError(f"no saved attempt outputs under {work_dir}")
    return attempts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retry-input", type=Path)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    validate_input_rows(rows)
    attempts = saved_bodies(args.work_dir)
    records: list[dict[str, Any]] = []
    retry_rows: list[dict[str, Any]] = []
    repairs = 0
    for row in rows:
        response = str(row.get("response") or "").strip()
        if not response:
            records.append({
                "schema_version": "pcsa-figure4-gpt4o-result-v1",
                "row_id": row["row_id"],
                "status": "not_applicable_no_response",
                "final_verdict": "SAFE",
            })
            continue
        errors: list[str] = []
        result: dict[str, Any] | None = None
        cid = custom_id(row["row_id"])
        for attempt, bodies in enumerate(attempts, 1):
            body = bodies.get(cid)
            if body is None:
                errors.append(f"attempt {attempt}: missing successful Batch response")
                continue
            raw, finish_reason, usage = response_text(body)
            try:
                judgment = parse_judgment(raw, response=response)
            except Exception as exc:
                errors.append(f"attempt {attempt}: {exc}")
                continue
            repairs += bool(judgment.get("evidence_compatibility_repair_used"))
            result = {
                "schema_version": "pcsa-figure4-gpt4o-result-v1",
                "row_id": row["row_id"],
                "status": "complete",
                "evaluator_model_requested": "gpt-4o",
                "evaluator_model_returned": body.get("model"),
                "target_field": "goal",
                **judgment,
                "raw": raw,
                "finish_reason": finish_reason,
                "usage": usage,
                "validation_attempt": attempt,
                "prior_errors": errors,
                "reprocessed_from_saved_batch": True,
            }
            break
        if result is None:
            result = {
                "schema_version": "pcsa-figure4-gpt4o-result-v1",
                "row_id": row["row_id"],
                "status": "invalid_evaluator_output",
                "errors": errors,
            }
            retry_rows.append(row)
        records.append(result)
    atomic_jsonl(args.output, records)
    if args.retry_input:
        atomic_jsonl(args.retry_input, retry_rows)
    print(json.dumps({
        "rows": len(records),
        "complete": len(records) - len(retry_rows),
        "invalid": len(retry_rows),
        "evidence_repairs": repairs,
    }))
    return 1 if retry_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())

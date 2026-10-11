#!/usr/bin/env python3
"""Convert one resumable external-baseline output cell to the eval schema."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import atomic_jsonl, mental_health_behavior
except ImportError:  # Direct execution from official_evaluation/.
    from common import atomic_jsonl, mental_health_behavior


def final_user_prompt(conversation: Any) -> str:
    if not isinstance(conversation, list):
        return ""
    for message in reversed(conversation):
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content") or "").strip()
    return ""


def load_case_ids(input_dir: Path) -> list[str]:
    manifest_path = input_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case_ids = manifest.get("case_ids")
    if not isinstance(case_ids, list) or not case_ids:
        raise ValueError(f"{manifest_path}: missing non-empty case_ids")
    normalized = [str(case_id) for case_id in case_ids]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{manifest_path}: duplicate case_ids")
    return normalized


def prepare(
    input_dir: Path,
    *,
    target_model: str,
    method: str,
    row_prefix: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_id in load_case_ids(input_dir):
        path = input_dir / f"{case_id}.json"
        if not path.exists():
            failure = input_dir / f"{case_id}.failed.json"
            suffix = " (failed checkpoint exists)" if failure.exists() else ""
            raise FileNotFoundError(f"missing result: {path}{suffix}")
        source = json.loads(path.read_text(encoding="utf-8"))
        case = source.get("case") or {}
        if str(case.get("case_id") or "") != case_id:
            raise ValueError(f"{path}: case_id mismatch")
        goal = str(case.get("objective") or "").strip()
        conversation = source.get("target_conversation") or []
        prompt = final_user_prompt(conversation)
        response = str(source.get("final_target_response") or "").strip() or None
        if not goal:
            raise ValueError(f"{path}: missing case.objective")
        if response and not prompt:
            raise ValueError(f"{path}: response exists but final user prompt is missing")
        rows.append(
            {
                "schema_version": "official-evaluation-input-v1",
                "row_id": f"{row_prefix}::{target_model}::{method}::{case_id}",
                "case_id": case_id,
                "attempt_id": "final",
                "method": method,
                "target_model": target_model,
                "crisis_label": case.get("crisis_label"),
                "persona": source.get("persona_context")
                or case.get("persona_context")
                or {},
                "behavior": mental_health_behavior(goal),
                "behavior_source": "mental_health_behavior_v1_from_case_objective",
                "goal": goal,
                "prompt": prompt,
                "response": response,
                "conversation_history": conversation,
                "harm_level": int(case.get("harm_level") or 2),
                "source_file": str(path.resolve()),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--target-model", required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--row-prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = prepare(
        args.input_dir,
        target_model=args.target_model,
        method=args.method,
        row_prefix=args.row_prefix,
    )
    atomic_jsonl(args.output, rows)
    print(json.dumps({"output": str(args.output.resolve()), "rows": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

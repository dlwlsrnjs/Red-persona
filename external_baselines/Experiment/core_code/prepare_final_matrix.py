#!/usr/bin/env python3
"""Convert an exact final research cohort matrix into the portable eval schema."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import atomic_jsonl, mental_health_behavior, read_jsonl


TARGETS = ("qwen7b_instruct", "gpt4o")
METHODS = (
    "direct",
    "skeleton_key",
    "many_shot",
    "red_teaming",
    "pair",
    "tap",
    "crescendo",
    "therapist_crescendo",
    "pcsa_phase2",
)


def final_user_prompt(conversation: Any) -> str:
    if not isinstance(conversation, list):
        return ""
    for message in reversed(conversation):
        if isinstance(message, dict) and message.get("role") == "user":
            return str(message.get("content") or "").strip()
    return ""


def prepare(
    input_dir: Path, cohort_index: Path, *, row_prefix: str = "final197"
) -> list[dict[str, Any]]:
    cohort = read_jsonl(cohort_index)
    case_ids = [str(row["case_id"]) for row in cohort]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("cohort contains duplicate case_id values")

    rows: list[dict[str, Any]] = []
    for target in TARGETS:
        for method in METHODS:
            cell_dir = input_dir / target / method
            for case_id in case_ids:
                path = cell_dir / f"{case_id}.json"
                if not path.exists():
                    failed = cell_dir / f"{case_id}.failed.json"
                    suffix = " (failed checkpoint exists)" if failed.exists() else ""
                    raise FileNotFoundError(f"missing result: {path}{suffix}")
                source = json.loads(path.read_text(encoding="utf-8"))
                case = source.get("case") or {}
                actual_case_id = str(case.get("case_id") or "")
                if actual_case_id != case_id:
                    raise ValueError(
                        f"{path}: case_id mismatch ({actual_case_id!r} != {case_id!r})"
                    )
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
                        "row_id": f"{row_prefix}::{target}::{method}::{case_id}",
                        "case_id": case_id,
                        "attempt_id": "final",
                        "method": method,
                        "target_model": target,
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
    expected = len(case_ids) * len(TARGETS) * len(METHODS)
    if len(rows) != expected:
        raise AssertionError(f"expected {expected} rows, built {len(rows)}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--cohort-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--row-prefix", default="final197")
    args = parser.parse_args()
    rows = prepare(args.input_dir, args.cohort_index, row_prefix=args.row_prefix)
    atomic_jsonl(args.output, rows)
    print(json.dumps({"output": str(args.output.resolve()), "rows": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

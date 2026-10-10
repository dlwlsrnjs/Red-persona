#!/usr/bin/env python3
"""Convert the completed external-baseline matrix to the portable eval schema."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from common import atomic_jsonl, mental_health_behavior


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


def load_cares_labels(path: Path | None) -> dict[tuple[str, str, str], str]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    labels: dict[tuple[str, str, str], str] = {}
    aliases = {
        "qwen7b_instruct": "Qwen/Qwen2.5-7B-Instruct",
        "gpt4o": "gpt-4o",
    }
    for row in value.get("rows", []):
        label = (row.get("cares") or {}).get("response_label")
        key = (str(row.get("target_model")), str(row.get("method")), str(row.get("case_id")))
        if label:
            labels[key] = str(label)
    return {
        (target, method, case_id): labels.get((aliases[target], method, case_id), "")
        for target in TARGETS
        for method in METHODS
        for case_id in {
            key[2] for key in labels if key[0] == aliases[target] and key[1] == method
        }
    }


def prepare(
    input_dir: Path,
    *,
    expected_per_cell: int,
    cares_results: Path | None,
) -> list[dict[str, Any]]:
    cares = load_cares_labels(cares_results)
    rows: list[dict[str, Any]] = []
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for target in TARGETS:
        for method in METHODS:
            paths = sorted((input_dir / target / method).glob("jmir-full-*.json"))
            if len(paths) != expected_per_cell:
                raise RuntimeError(
                    f"{target}/{method}: expected {expected_per_cell} files, found {len(paths)}"
                )
            for path in paths:
                source = json.loads(path.read_text(encoding="utf-8"))
                case = source.get("case") or {}
                case_id = str(case.get("case_id") or path.stem)
                goal = str(case.get("objective") or "").strip()
                prompt = final_user_prompt(source.get("target_conversation"))
                response = str(source.get("final_target_response") or "").strip() or None
                if not goal:
                    raise ValueError(f"{path}: missing case.objective")
                if response and not prompt:
                    raise ValueError(f"{path}: response exists but final user prompt is missing")
                row = {
                    "schema_version": "official-evaluation-input-v1",
                    "row_id": f"external::{target}::{method}::{case_id}",
                    "case_id": case_id,
                    "attempt_id": "final",
                    "method": method,
                    "target_model": target,
                    "crisis_label": case.get("crisis_label"),
                    "persona": source.get("persona_context") or case.get("persona_context") or {},
                    "behavior": mental_health_behavior(goal),
                    "behavior_source": "mental_health_behavior_v1_from_case_objective",
                    "goal": goal,
                    "prompt": prompt,
                    "response": response,
                    "conversation_history": source.get("target_conversation") or [],
                    "harm_level": 2,
                    "source_file": str(path.resolve()),
                }
                label = cares.get((target, method, case_id))
                if label:
                    row["cares_label"] = label
                    row["cares_label_source"] = str(cares_results.resolve())
                rows.append(row)
                counts[(target, method)] += 1
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-per-cell", type=int, default=500)
    parser.add_argument("--cares-results", type=Path)
    args = parser.parse_args()
    rows = prepare(
        args.input_dir,
        expected_per_cell=args.expected_per_cell,
        cares_results=args.cares_results,
    )
    atomic_jsonl(args.output, rows)
    print(json.dumps({"output": str(args.output.resolve()), "rows": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

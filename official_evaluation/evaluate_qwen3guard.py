#!/usr/bin/env python3
"""Evaluate portable response rows with Qwen3Guard-Gen as an auxiliary axis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from common import in_shard, read_jsonl, validate_input_rows


DEFAULT_MODEL = "Qwen/Qwen3Guard-Gen-8B"


def existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {str(row["row_id"]) for row in read_jsonl(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.num_shards:
        parser.error("--shard-index must be in [0, --num-shards)")

    # Reuse the audited parser and official chat-template invocation used by
    # the method's existing auxiliary-safety experiments.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "persona_redteam"))
    from experiments.evaluate_qwen3guard_direct_response import classify_local

    source = read_jsonl(args.input)
    validate_input_rows(source)
    source = [
        row
        for row in source
        if in_shard(row["row_id"], args.shard_index, args.num_shards)
    ]
    done = existing_ids(args.output)
    pending = [row for row in source if row["row_id"] not in done]
    classifier_rows = [
        {
            "row_id": row["row_id"],
            "case_id": row["case_id"],
            "condition": row["target_model"],
            "direction": row["method"],
            "attack_style": row["method"],
            "prompt": row["prompt"],
            "response": str(row.get("response") or ""),
            "bridge_available": bool(str(row.get("response") or "").strip()),
            "private_goal_leak": None,
        }
        for row in pending
    ]
    scored = classify_local(
        classifier_rows,
        model_name=args.model,
        batch_size=args.batch_size,
        device=args.device,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as handle:
        for row in scored:
            handle.write(
                json.dumps(
                    {
                        "schema_version": "qwen3guard-official-eval-v1",
                        "row_id": row["row_id"],
                        "status": row["evaluation_status"],
                        "safety": row["safety"],
                        "categories": row["categories"],
                        "refusal": row["refusal"],
                        "unsafe_positive": row["unsafe_positive"],
                        "risk_positive": row["risk_positive"],
                        "self_harm_category": row["self_harm_category"],
                        "refusal_detected": row["refusal_detected"],
                        "parse_error": row["parse_error"],
                        "classifier_model": args.model,
                        "classifier_raw": row["classifier_raw"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        handle.flush()
    invalid = sum(row["evaluation_status"] == "parse_error" for row in scored)
    print(
        json.dumps(
            {
                "new_results": len(scored),
                "unsafe": sum(row["unsafe_positive"] for row in scored),
                "risk": sum(row["risk_positive"] for row in scored),
                "invalid": invalid,
            }
        )
    )
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())

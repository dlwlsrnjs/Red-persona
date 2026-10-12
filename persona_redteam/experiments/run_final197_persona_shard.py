"""Run one final197 persona shard until every case passes all quality gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POOL_ROOT = ROOT.parent / "data/personas"
sys.path.insert(0, str(ROOT))

from pipeline.runtime_io import atomic_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--qwen-base-url", required=True)
    parser.add_argument("--max-rewrite-rounds", type=int, default=8)
    parser.add_argument("--seed", type=int, default=47)
    args = parser.parse_args()
    if args.max_rewrite_rounds < 1:
        parser.error("--max-rewrite-rounds must be at least 1")

    total = len(json.loads(args.cases.read_text(encoding="utf-8")))
    log_path = args.checkpoint_dir / "rewrite_rounds.json"
    rounds = []
    if log_path.exists():
        value = json.loads(log_path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("rounds"), list):
            rounds = value["rounds"]
    start_round = max((int(row["round"]) for row in rounds), default=0) + 1

    for rewrite_round in range(start_round, args.max_rewrite_rounds + 1):
        command = [
            sys.executable, "-m", "pipeline.generate_histories",
            "--cases", str(args.cases),
            "--profiles", str(POOL_ROOT / "personas.jsonl"),
            "--category-labels", str(POOL_ROOT / "persona_category_labels.jsonl"),
            "--generation-prompt", str(
                ROOT / "configs/persona_history/generation_prompt.template.txt"),
            "--coverage-prompt", str(
                ROOT / "configs/persona_history/coverage_prompt.template.txt"),
            "--output", str(args.output),
            "--checkpoint-dir", str(args.checkpoint_dir),
            "--model", "Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2",
            "--base-url", args.base_url,
            "--qwen-model", "Qwen/Qwen2.5-7B-Instruct",
            "--qwen-base-url", args.qwen_base_url,
            "--retry-failed", "--seed", str(args.seed),
            "--rewrite-round", str(rewrite_round),
            "--top-k", "12", "--min-turns", "4", "--max-turns", "12",
            "--generation-attempts", "8",
        ]
        completed = subprocess.run(command, cwd=ROOT, check=False)
        generated = []
        if args.output.exists():
            generated = json.loads(args.output.read_text(encoding="utf-8"))
        summary_path = args.checkpoint_dir / "summary.json"
        summary = (json.loads(summary_path.read_text(encoding="utf-8"))
                   if summary_path.exists() else {})
        round_record = {
            "round": rewrite_round,
            "effective_seed": args.seed + (rewrite_round - 1) * 1000003,
            "returncode": completed.returncode,
            "complete": len(generated),
            "total": total,
            "failed_case_ids": summary.get("failed_case_ids", []),
        }
        rounds.append(round_record)
        atomic_json(log_path, {
            "policy": "rewrite failed cases with a new effective seed until every mandatory quality dimension passes",
            "quality_threshold": 1.0,
            "max_rewrite_rounds": args.max_rewrite_rounds,
            "rounds": rounds,
        })
        print(json.dumps(round_record, ensure_ascii=False), flush=True)
        if len(generated) == total and completed.returncode == 0:
            return
    raise SystemExit(
        f"quality threshold not reached after {args.max_rewrite_rounds} rewrite rounds"
    )


if __name__ == "__main__":
    main()

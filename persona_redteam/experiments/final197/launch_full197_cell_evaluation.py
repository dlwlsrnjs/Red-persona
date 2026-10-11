"""Merge and Batch-score one completed Final-197 matrix cell."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential
from experiments.final197.launch_full197_arm import ARMS, MATRIX_ID, TARGETS
from experiments.merge_run_shards import merge_shards
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    campaign = ROOT / "data/evaluations" / MATRIX_ID / args.target / args.arm
    result = ROOT / "result/OURS" / MATRIX_ID / args.target / args.arm
    merged = result / "merged"
    lanes = [result / f"lane_{index}" for index in range(8)]
    merge_summary = merge_shards(lanes, merged, 197)
    target_model = (
        "gpt-4o-2024-11-20" if args.target == "gpt4o"
        else "Qwen/Qwen2.5-7B-Instruct"
    )
    score_root = campaign / "scoring"
    score_root.mkdir(parents=True, exist_ok=True)
    keys = {
        "OPENAI_API_KEY": credential("OPENAI_API_KEY"),
        "OPENAI_API_KEY2": credential("OPENAI_API_KEY2"),
    }
    jobs = (
        (
            "cares_jmir", keys["OPENAI_API_KEY"],
            [
                sys.executable, "-m", "experiments.evaluate_final_cares_pilot64",
                "--run-dir", str(merged), "--selection", str(campaign / "selection.json"),
                "--output-dir", str(score_root / "cares_jmir"),
                "--api-mode", "batch", "--expected-cases", "197",
                "--target-model", target_model, "--workers", "128",
                "--max-budget-usd", "60", "--poll-seconds", "20", "--execute",
            ],
        ),
        (
            "recovery_behavior", keys["OPENAI_API_KEY2"],
            [
                sys.executable, "-m", "experiments.evaluate_recovery_behavior_batch",
                "--run-dir", str(merged),
                "--output", str(score_root / "recovery_behavior.json"),
                "--expected-cases", "197", "--api-mode", "batch",
                "--workers", "128", "--max-budget-usd", "60",
                "--poll-seconds", "20", "--execute",
            ],
        ),
    )
    processes = []
    launched = []
    for name, key, command in jobs:
        log_path = score_root / f"{name}.log"
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = key
        log_handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command, cwd=ROOT, env=env,
            stdout=log_handle, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_handle.close()
        processes.append((name, process))
        launched.append({"name": name, "pid": process.pid, "log": str(log_path)})
    atomic_json(score_root / "launch_manifest.json", {
        "version": "final197-matrix-batch-scoring-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "target": args.target, "arm": args.arm, "target_model": target_model,
        "merged_run": str(merged), "merge_summary": merge_summary,
        "credentials_persisted": False, "jobs": launched,
    })
    print(json.dumps({
        "target": args.target, "arm": args.arm,
        "merged": str(merged), "jobs": launched,
    }, ensure_ascii=False), flush=True)
    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print(json.dumps({
            "target": args.target, "arm": args.arm,
            "status": "scoring_exited", "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failed = {name: code for name, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

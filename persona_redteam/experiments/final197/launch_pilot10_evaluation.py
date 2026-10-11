"""Merge a complete pilot-10 run and launch Batch-based scoring in two lanes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential
from experiments.merge_run_shards import merge_shards
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "result/OURS/final197_explicit_goal_pilot10_gpt4o_v1"
DEFAULT_CAMPAIGN_ROOT = (
    ROOT / "data/evaluations/final197_explicit_goal_pilot10_gpt4o_v1"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--campaign-root", type=Path, default=DEFAULT_CAMPAIGN_ROOT)
    parser.add_argument(
        "--lane1-override", type=Path,
        help="Use a separately repaired lane_1 directory while preserving originals.",
    )
    parser.add_argument(
        "--wait", action="store_true",
        help="Keep the launcher attached until both scoring jobs exit.",
    )
    args = parser.parse_args()

    merged = args.run_root / "merged"
    lane_dirs = [args.run_root / f"lane_{index}" for index in range(4)]
    if args.lane1_override:
        lane_dirs[1] = args.lane1_override
    summary = merge_shards(lane_dirs, merged, 10)
    selection = args.campaign_root / "selection.json"
    score_root = args.campaign_root / "scoring"
    score_root.mkdir(parents=True, exist_ok=True)
    keys = {
        "OPENAI_API_KEY": credential("OPENAI_API_KEY"),
        "OPENAI_API_KEY2": credential("OPENAI_API_KEY2"),
    }

    jobs = (
        (
            "cares_jmir",
            keys["OPENAI_API_KEY"],
            [
                sys.executable, "-m", "experiments.evaluate_final_cares_pilot64",
                "--run-dir", str(merged),
                "--selection", str(selection),
                "--output-dir", str(score_root / "cares_jmir"),
                "--api-mode", "batch",
                "--expected-cases", "10",
                "--target-model", "gpt-4o-2024-11-20",
                "--workers", "128",
                "--max-budget-usd", "30",
                "--poll-seconds", "10",
                "--execute",
            ],
        ),
        (
            "recovery_behavior",
            keys["OPENAI_API_KEY2"],
            [
                sys.executable, "-m", "experiments.evaluate_recovery_behavior_batch",
                "--run-dir", str(merged),
                "--output", str(score_root / "recovery_behavior.json"),
                "--expected-cases", "10",
                "--api-mode", "batch",
                "--workers", "128",
                "--max-budget-usd", "30",
                "--poll-seconds", "10",
                "--execute",
            ],
        ),
    )
    launched = []
    processes = []
    for name, key, command in jobs:
        log_path = score_root / f"{name}.log"
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = key
        log_handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_handle.close()
        processes.append((name, process))
        launched.append({"name": name, "pid": process.pid, "log": str(log_path)})
    record = {
        "protocol": "final197-explicit-goal-pilot10-scoring-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "merged_run": str(merged),
        "merge_summary": summary,
        "api_mode": "openai_batch",
        "credentials_persisted": False,
        "jobs": launched,
    }
    atomic_json(score_root / "launch_manifest.json", record)
    print(record)
    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print({"status": "all_scoring_jobs_exited",
               "return_codes": return_codes}, flush=True)
        failed = {name: code for name, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

"""Evaluate both completed goal-exposure pilot arms through Batch scorers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ROOT = (
    ROOT / "data/evaluations/final197_goal_exposure_pair_pilot10_gpt4o_v18"
)
RESULT_ROOT = (
    ROOT / "result/OURS/final197_goal_exposure_pair_pilot10_gpt4o_v18"
)
ARMS = ("no_verbatim", "explicit")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    processes = []
    for arm in ARMS:
        command = [
            sys.executable, "-m",
            "experiments.final197.launch_pilot10_evaluation",
            "--goal-exposure", arm,
            "--run-root", str(RESULT_ROOT / arm),
            "--campaign-root", str(CAMPAIGN_ROOT / arm),
            "--wait",
        ]
        process = subprocess.Popen(command, cwd=ROOT)
        processes.append((arm, process))
    if args.wait:
        return_codes = {arm: process.wait() for arm, process in processes}
        print(json.dumps({
            "status": "paired_evaluation_exited",
            "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failed = {arm: code for arm, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

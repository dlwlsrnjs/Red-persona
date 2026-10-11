"""Wait for generation, score all cells, release Llama GPUs, then run local guards."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from experiments.final197.launch_full197_arm import ARMS, MATRIX_ID, TARGETS


ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = ROOT / "result/OURS" / MATRIX_ID


def generation_complete() -> bool:
    for target in TARGETS:
        for arm in ARMS:
            root = RESULT_ROOT / target / arm
            if len(list(root.glob("lane_*/run_summary.json"))) != 8:
                return False
            artifacts = [
                path for path in root.glob("lane_*/*.json")
                if path.name != "run_summary.json"
            ]
            if len(artifacts) != 197:
                return False
    return True


def stop_llama_manager(pid: int) -> None:
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if not cmdline_path.exists():
        return
    cmdline = cmdline_path.read_bytes().replace(b"\0", b" ").decode(
        "utf-8", errors="replace"
    )
    if "experiments.final197.launch_cross_target_replicas" not in cmdline:
        raise RuntimeError(f"PID {pid} is not the registered Llama replica manager")
    os.kill(pid, signal.SIGINT)
    for _ in range(120):
        if not cmdline_path.exists():
            return
        time.sleep(1)
    raise RuntimeError("Llama replica manager did not exit after SIGINT")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--llama-manager-pid", type=int, required=True)
    args = parser.parse_args()
    while not generation_complete():
        print(json.dumps({
            "status": "waiting_for_generation", "matrix_id": MATRIX_ID,
        }), flush=True)
        time.sleep(args.poll_seconds)
    subprocess.run([
        sys.executable, "-m",
        "experiments.final197.launch_full197_matrix_evaluation", "--wait",
    ], cwd=ROOT, check=True)
    stop_llama_manager(args.llama_manager_pid)
    subprocess.run([
        sys.executable, "-m",
        "experiments.final197.launch_full197_local_safety_matrix",
    ], cwd=ROOT, check=True)
    print(json.dumps({
        "status": "all_generation_and_scoring_complete", "matrix_id": MATRIX_ID,
    }), flush=True)


if __name__ == "__main__":
    main()

"""Launch CARES/JMIR and recovery/behavior scoring for all six cells."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from experiments.final197.launch_full197_arm import ARMS, TARGETS


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    processes = []
    for target in TARGETS:
        for arm in ARMS:
            process = subprocess.Popen([
                sys.executable, "-m",
                "experiments.final197.launch_full197_cell_evaluation",
                "--target", target, "--arm", arm, "--wait",
            ], cwd=ROOT)
            processes.append((f"{target}/{arm}", process))
    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print(json.dumps({
            "status": "matrix_scoring_exited", "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failed = {name: code for name, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

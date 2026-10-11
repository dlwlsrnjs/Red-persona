"""Wait for all cloud scoring artifacts, then run the eight-GPU local safety matrix."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from experiments.final197.launch_full197_arm import ARMS, MATRIX_ID, TARGETS


ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ROOT = ROOT / "data/evaluations" / MATRIX_ID


def required_scoring_outputs() -> list[Path]:
    outputs = []
    for target in TARGETS:
        for arm in ARMS:
            scoring = CAMPAIGN_ROOT / target / arm / "scoring"
            outputs.extend((
                scoring / "cares_jmir" / "results.json",
                scoring / "recovery_behavior.json",
            ))
    return outputs


def missing_outputs() -> list[Path]:
    return [path for path in required_scoring_outputs() if not path.is_file()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.poll_seconds < 1:
        raise ValueError("poll-seconds must be positive")

    while True:
        missing = missing_outputs()
        print(json.dumps({
            "status": "ready" if not missing else "waiting_for_cloud_scoring",
            "complete_outputs": 12 - len(missing),
            "expected_outputs": 12,
            "missing": [str(path.relative_to(ROOT)) for path in missing],
        }, ensure_ascii=False), flush=True)
        if args.check_only or not missing:
            break
        time.sleep(args.poll_seconds)

    if missing or args.check_only:
        return
    subprocess.run([
        sys.executable, "-m",
        "experiments.final197.launch_full197_local_safety_matrix",
    ], cwd=ROOT, check=True)
    print(json.dumps({
        "status": "all_local_safety_scoring_complete",
        "matrix_id": MATRIX_ID,
    }), flush=True)


if __name__ == "__main__":
    main()

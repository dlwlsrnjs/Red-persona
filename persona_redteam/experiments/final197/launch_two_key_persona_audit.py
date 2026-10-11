"""Run the 197-case GPT-4o-mini persona audit with 128 total workers."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "full_v49_parallel/persona_cases.json"
)
DEFAULT_OUTPUT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "full_v49_parallel/gpt4omini_match_audit"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=128)
    parser.add_argument("--split", type=int, default=99)
    args = parser.parse_args()
    if args.workers < 2:
        parser.error("--workers must be at least 2")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    keys = (credential("OPENAI_API_KEY"), credential("OPENAI_API_KEY2"))
    lane_workers = (args.workers // 2, args.workers - args.workers // 2)
    processes = []
    for lane, start, stop, key, workers in (
        ("lane_a", 0, args.split, keys[0], lane_workers[0]),
        ("lane_b", args.split, 197, keys[1], lane_workers[1]),
    ):
        command = [
            sys.executable, "-m", "experiments.final197.audit_persona_match_gpt4omini",
            "--cases", str(args.cases),
            "--output", str(args.output_dir / f"{lane}.json"),
            "--checkpoint-dir", str(args.output_dir / "checkpoints" / lane),
            "--start", str(start), "--stop", str(stop),
            "--workers", str(workers),
        ]
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = key
        processes.append((lane, subprocess.Popen(command, cwd=ROOT, env=env)))
    failures = [(lane, process.wait()) for lane, process in processes]
    failures = [(lane, code) for lane, code in failures if code]
    if failures:
        raise SystemExit(f"persona audit lanes failed: {failures}")
    subprocess.run([
        sys.executable, "-m", "experiments.final197.merge_persona_match_audit",
        "--audit-dir", str(args.output_dir),
    ], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()

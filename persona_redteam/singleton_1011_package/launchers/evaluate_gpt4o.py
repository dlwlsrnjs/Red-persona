"""Run GPT-4o Batch CARES/JMIR and R/B evaluation for a merged singleton run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from _bootstrap import DEFAULT_WORKSPACE_ROOT, PACKAGE_ROOT, SOURCE_ROOT, subprocess_env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--baselines", type=Path, default=(
        DEFAULT_WORKSPACE_ROOT / "data/final_cares_h1_h2/pilot64/baseline64_reference.json"
    ))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-cases", type=int, default=197)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    common = ["--api-mode", "batch", "--expected-cases", str(args.expected_cases),
              "--workers", "128", "--max-budget-usd", "60", "--poll-seconds", "20"]
    jobs = [
        ("cares_jmir", "OPENAI_API_KEY", [
            sys.executable, "-m", "experiments.evaluate_final_cares_pilot64",
            "--run-dir", str(args.run_dir), "--selection", str(args.selection),
            "--baselines", str(args.baselines), "--output-dir", str(args.output_dir / "cares_jmir"),
            "--target-model", "gpt-4o-2024-11-20", "--evaluator-model", "gpt-4o-2024-11-20",
            *common,
        ]),
        ("recovery_behavior", "OPENAI_API_KEY2", [
            sys.executable, "-m", "experiments.evaluate_recovery_behavior_batch",
            "--run-dir", str(args.run_dir), "--output", str(args.output_dir / "recovery_behavior.json"),
            "--model", "gpt-4o-2024-11-20", *common,
        ]),
    ]
    if args.execute:
        for _, _, command in jobs:
            command.append("--execute")
    if not args.execute:
        for name, _, command in jobs:
            print(json.dumps({"preflight": name}, ensure_ascii=False))
            subprocess.run(command, cwd=SOURCE_ROOT, env=subprocess_env(), check=True)
        return
    processes = []
    for name, key_name, command in jobs:
        log = (args.output_dir / f"{name}.log").open("ab", buffering=0)
        process = subprocess.Popen(command, cwd=SOURCE_ROOT, env=subprocess_env(key_name),
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        log.close()
        processes.append((name, process))
    print(json.dumps({"jobs": [{"name": name, "pid": process.pid}
                                for name, process in processes]}, ensure_ascii=False))
    if args.wait:
        codes = {name: process.wait() for name, process in processes}
        if any(codes.values()):
            raise SystemExit(max(codes.values()))


if __name__ == "__main__":
    main()


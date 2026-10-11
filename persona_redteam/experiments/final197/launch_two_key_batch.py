"""Launch the frozen Final-197 target run in two resumable API-key lanes.

No credential is written to disk. Lane A inherits OPENAI_API_KEY; lane B maps
OPENAI_API_KEY2 to OPENAI_API_KEY only in its child process.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "full_v49_parallel/FINAL197_PERSONAS_WITH_HISTORY_AND_EXPLICIT_GOAL.json"
)
DEFAULT_RUN = ROOT / "data/evaluations/final197_gpt4o_clinical_v1"
DEFAULT_RESULTS = ROOT / "result/OURS/final197_gpt4o_clinical_v1"


def base_command(cases: Path, selection: Path) -> list[str]:
    return [
        sys.executable, "-m", "experiments.final197.run_locked_gpt4o",
        "--cases", str(cases),
        "--selection-path", str(selection),
        "--selection-key", "case_ids",
        "--max-budget-usd", "120",
        "--poll-seconds", "20",
    ]


def validate_cases(path: Path) -> None:
    cases = json.loads(path.read_text(encoding="utf-8"))
    ids = [str(case.get("case_id", "")) for case in cases]
    if len(ids) != 197 or len(set(ids)) != 197:
        raise ValueError("the locked target run requires exactly 197 unique cases")
    failures = []
    for case in cases:
        gate = case.get("persona_history_generation", {}).get("final_quality_gate", {})
        if gate.get("passed") is not True or gate.get("score") != 1.0:
            failures.append(str(case.get("case_id", "<unknown>")))
    if failures:
        raise ValueError("persona quality gate failed: " + ", ".join(failures[:5]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--campaign-root", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--result-root", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--split", type=int, default=99)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.split < 197:
        parser.error("--split must be between 1 and 196")
    validate_cases(args.cases)
    primary = credential("OPENAI_API_KEY")
    secondary = None if args.prepare_only else credential("OPENAI_API_KEY2")

    args.campaign_root.mkdir(parents=True, exist_ok=True)
    args.result_root.mkdir(parents=True, exist_ok=True)
    selection = args.campaign_root / "selection.json"

    prepare = [
        *base_command(args.cases, selection),
        "--campaign-dir", str(args.campaign_root / "prepare"),
        "--output-dir", str(args.result_root / "prepare"),
        "--prepare-only",
    ]
    completed = subprocess.run(prepare, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    if args.prepare_only:
        return

    lanes = []
    for name, start, stop, key in (
        ("lane_a", 0, args.split, primary),
        ("lane_b", args.split, 197, secondary),
    ):
        command = [
            *base_command(args.cases, selection),
            "--campaign-dir", str(args.campaign_root / name),
            "--output-dir", str(args.result_root / name),
            "--start", str(start), "--stop", str(stop),
        ]
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = key
        process = subprocess.Popen(command, cwd=ROOT, env=env)
        lanes.append({"lane": name, "pid": process.pid, "start": start, "stop": stop})
    manifest = {
        "protocol": "final197_gpt4o_clinical_v1",
        "selection": str(selection),
        "lanes": lanes,
        "credentials_persisted": False,
    }
    (args.campaign_root / "two_key_launch.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()

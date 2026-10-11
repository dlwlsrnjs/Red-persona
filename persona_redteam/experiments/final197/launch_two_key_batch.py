"""Launch the frozen Final-197 target run in eight resumable two-key lanes.

No credential is written to disk. The two credentials are alternated across
eight lanes, each backed by one already-running Qwen researcher endpoint.
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
        "--max-budget-usd", "60",
        "--poll-seconds", "20",
    ]


LANES = (
    ("lane_0", 0, 25, "http://127.0.0.1:8000/v1", "OPENAI_API_KEY"),
    ("lane_1", 25, 50, "http://127.0.0.1:8001/v1", "OPENAI_API_KEY2"),
    ("lane_2", 50, 75, "http://127.0.0.1:8012/v1", "OPENAI_API_KEY"),
    ("lane_3", 75, 100, "http://127.0.0.1:8022/v1", "OPENAI_API_KEY2"),
    ("lane_4", 100, 125, "http://127.0.0.1:8002/v1", "OPENAI_API_KEY"),
    ("lane_5", 125, 149, "http://127.0.0.1:8003/v1", "OPENAI_API_KEY2"),
    ("lane_6", 149, 173, "http://127.0.0.1:8010/v1", "OPENAI_API_KEY"),
    ("lane_7", 173, 197, "http://127.0.0.1:8020/v1", "OPENAI_API_KEY2"),
)


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
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--wait", action="store_true",
        help="Keep the launcher attached until every lane exits.",
    )
    args = parser.parse_args()
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

    credentials = {"OPENAI_API_KEY": primary, "OPENAI_API_KEY2": secondary}
    lanes = []
    processes = []
    for name, start, stop, researcher_url, key_name in LANES:
        command = [
            *base_command(args.cases, selection),
            "--campaign-dir", str(args.campaign_root / name),
            "--output-dir", str(args.result_root / name),
            "--researcher-base-url", researcher_url,
            "--researcher-workers", "32",
            "--start", str(start), "--stop", str(stop),
        ]
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = credentials[key_name]
        log_path = args.campaign_root / f"{name}.log"
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
        lanes.append({
            "lane": name,
            "pid": process.pid,
            "start": start,
            "stop": stop,
            "researcher_base_url": researcher_url,
            "credential_name": key_name,
            "log": str(log_path),
        })
    manifest = {
        "protocol": "final197_gpt4o_clinical_v1_eight_lane_batch",
        "selection": str(selection),
        "lanes": lanes,
        "credentials_persisted": False,
    }
    (args.campaign_root / "two_key_launch.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))
    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print(json.dumps({
            "status": "all_lanes_exited",
            "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failed = {name: code for name, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

"""Merge and Batch-score both failed-23 1011 pilot arms on data1."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential
from experiments.merge_run_shards import merge_shards
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = Path(
    "/data1/users/ljk98/runtime_cache/persona_redteam_final197/"
    "failed23_1011_method_v1"
)
ARMS = ("no_verbatim", "no_history")
EXPECTED_CASES = 23
TARGET_MODEL = "Qwen/Qwen2.5-7B-Instruct"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    selection = args.runtime / "selection_failed23.json"
    if not selection.exists():
        raise FileNotFoundError(selection)
    keys = {
        "OPENAI_API_KEY": credential("OPENAI_API_KEY"),
        "OPENAI_API_KEY2": credential("OPENAI_API_KEY2"),
    }
    commands: list[tuple[str, str, list[str], Path]] = []
    merge_summaries = {}
    for arm in ARMS:
        lane_dirs = [
            args.runtime / "results" / arm / f"lane_{lane}"
            for lane in range(4)
        ]
        merged = args.runtime / "merged" / arm
        merge_summaries[arm] = merge_shards(
            lane_dirs, merged, EXPECTED_CASES
        )
        scoring = args.runtime / "scoring" / arm
        scoring.mkdir(parents=True, exist_ok=True)
        cares_key = "OPENAI_API_KEY" if arm == "no_verbatim" else "OPENAI_API_KEY2"
        recovery_key = "OPENAI_API_KEY2" if arm == "no_verbatim" else "OPENAI_API_KEY"
        cares_command = [
            sys.executable,
            "-m",
            "experiments.evaluate_final_cares_pilot64",
            "--run-dir",
            str(merged),
            "--selection",
            str(selection),
            "--output-dir",
            str(scoring / "cares_jmir"),
            "--api-mode",
            "batch",
            "--expected-cases",
            str(EXPECTED_CASES),
            "--target-model",
            TARGET_MODEL,
            "--workers",
            "128",
            "--max-budget-usd",
            "30",
            "--poll-seconds",
            "10",
        ]
        recovery_command = [
            sys.executable,
            "-m",
            "experiments.evaluate_recovery_behavior_batch",
            "--run-dir",
            str(merged),
            "--output",
            str(scoring / "recovery_behavior.json"),
            "--expected-cases",
            str(EXPECTED_CASES),
            "--api-mode",
            "batch",
            "--workers",
            "128",
            "--max-budget-usd",
            "30",
            "--poll-seconds",
            "10",
        ]
        if not args.prepare_only:
            cares_command.append("--execute")
            recovery_command.append("--execute")
        commands.extend((
            (f"{arm}/cares_jmir", cares_key, cares_command,
             scoring / "cares_jmir.log"),
            (f"{arm}/recovery_behavior", recovery_key, recovery_command,
             scoring / "recovery_behavior.log"),
        ))

    temp_dir = args.runtime / "tmp"
    pycache_dir = args.runtime / "pycache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    pycache_dir.mkdir(parents=True, exist_ok=True)
    processes = []
    launched = []
    for name, key_name, command, log_path in commands:
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = keys[key_name]
        env["TMPDIR"] = str(temp_dir)
        env["PYTHONPYCACHEPREFIX"] = str(pycache_dir)
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
        launched.append({
            "name": name,
            "pid": process.pid,
            "credential_name": key_name,
            "log": str(log_path),
        })
    manifest = {
        "version": "failed23-1011-method-scoring-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "prepare_only": args.prepare_only,
        "api_mode": "openai_batch",
        "credentials_persisted": False,
        "merge_summaries": merge_summaries,
        "jobs": launched,
    }
    atomic_json(args.runtime / "scoring" / "launch_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    return_codes = {name: process.wait() for name, process in processes}
    atomic_json(args.runtime / "scoring" / "completion.json", {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "prepare_only": args.prepare_only,
        "return_codes": return_codes,
    })
    print(json.dumps({
        "status": "complete", "return_codes": return_codes,
    }, ensure_ascii=False), flush=True)
    if any(return_codes.values()):
        raise SystemExit(max(return_codes.values()))


if __name__ == "__main__":
    main()

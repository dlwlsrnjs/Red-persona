"""Batch-score the merged failed-23 three-arm attack-turn experiment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential
from experiments.final197.launch_failed23_1011_pilot import QWEN_MODEL
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = Path(
    "/data1/users/ljk98/runtime_cache/persona_redteam_final197/"
    "failed23_attack_turn_ablation_v7"
)
SELECTION = Path(
    "/data1/users/ljk98/runtime_cache/persona_redteam_final197/"
    "failed23_1011_method_v1/selection_failed23.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    merged = args.runtime / "merged"
    if not (merged / "run_summary.json").exists():
        raise FileNotFoundError(merged / "run_summary.json")
    scoring = args.runtime / "scoring" / "cares_jmir"
    scoring.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "experiments.evaluate_attack_turn_ablation",
        "--output-root",
        str(merged),
        "--selection",
        str(SELECTION),
        "--output-dir",
        str(scoring),
        "--api-mode",
        "batch",
        "--expected-cases",
        "23",
        "--target-model",
        QWEN_MODEL,
        "--workers",
        "128",
        "--max-budget-usd",
        "30",
        "--poll-seconds",
        "10",
    ]
    if not args.prepare_only:
        command.append("--execute")

    runtime_tmp = args.runtime / "tmp"
    pycache = args.runtime / "pycache"
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    pycache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = credential("OPENAI_API_KEY")
    env["TMPDIR"] = str(runtime_tmp)
    env["PYTHONPYCACHEPREFIX"] = str(pycache)
    log_path = scoring / "evaluation.log"
    with log_path.open("ab", buffering=0) as handle:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    manifest = {
        "version": "failed23-attack-turn-evaluation-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "prepare_only": args.prepare_only,
        "api_mode": "openai_batch",
        "credentials_persisted": False,
        "pid": process.pid,
        "command_without_secret": command,
        "log": str(log_path),
    }
    atomic_json(scoring / "launch_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    return_code = process.wait()
    completion = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "return_code": return_code,
    }
    atomic_json(scoring / "completion.json", completion)
    print(json.dumps(completion, ensure_ascii=False), flush=True)
    if return_code:
        raise SystemExit(return_code)


if __name__ == "__main__":
    main()

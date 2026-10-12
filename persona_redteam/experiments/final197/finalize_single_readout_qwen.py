#!/usr/bin/env python3
"""Merge and score one portable Final-197 Qwen short-readout arm."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiments.final197.credentials import credential
from experiments.merge_run_shards import merge_shards
from pipeline.runtime_io import atomic_json


CAMPAIGN_ID = "final197_single_readout_qwen_v2"
ARMS = ("with_history", "no_history")
TARGET_MODEL = "Qwen/Qwen2.5-7B-Instruct"
EVALUATOR_MODEL = "gpt-4o-2024-11-20"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def run_logged(
    command: list[str],
    log_path: Path,
    environment: dict[str, str],
    *,
    wait: bool,
) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab", buffering=0)
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=not wait,
    )
    handle.close()
    return process


def merge(
    result_root: Path,
    lane_count: int,
    expected_cases: int,
) -> tuple[Path, dict]:
    merged = result_root / "merged"
    lanes = [result_root / f"lane_{index}" for index in range(lane_count)]
    missing = [path for path in lanes if not (path / "run_summary.json").is_file()]
    if missing:
        raise FileNotFoundError(
            "generation lanes are incomplete: " + ", ".join(map(str, missing))
        )
    return merged, merge_shards(lanes, merged, expected_cases)


def launch_cloud(
    merged: Path,
    selection: Path,
    score_root: Path,
    expected_cases: int,
    credential_name: str,
    recovery_credential_name: str,
    wait: bool,
) -> None:
    score_root.mkdir(parents=True, exist_ok=True)
    jobs = (
        (
            "cares_jmir",
            credential_name,
            [
                sys.executable,
                "-m",
                "experiments.evaluate_final_cares_pilot64",
                "--run-dir",
                str(merged),
                "--selection",
                str(selection),
                "--output-dir",
                str(score_root / "cares_jmir"),
                "--api-mode",
                "batch",
                "--evaluator-model",
                EVALUATOR_MODEL,
                "--expected-cases",
                str(expected_cases),
                "--target-model",
                TARGET_MODEL,
                "--workers",
                "128",
                "--max-budget-usd",
                "60",
                "--poll-seconds",
                "20",
                "--execute",
            ],
        ),
        (
            "recovery_behavior",
            recovery_credential_name,
            [
                sys.executable,
                "-m",
                "experiments.evaluate_recovery_behavior_batch",
                "--run-dir",
                str(merged),
                "--output",
                str(score_root / "recovery_behavior.json"),
                "--model",
                EVALUATOR_MODEL,
                "--expected-cases",
                str(expected_cases),
                "--api-mode",
                "batch",
                "--workers",
                "128",
                "--max-budget-usd",
                "60",
                "--poll-seconds",
                "20",
                "--execute",
            ],
        ),
    )
    processes: list[tuple[str, subprocess.Popen]] = []
    launched = []
    for name, key_name, command in jobs:
        environment = os.environ.copy()
        environment["OPENAI_API_KEY"] = credential(key_name)
        process = run_logged(
            command,
            score_root / f"{name}.log",
            environment,
            wait=wait,
        )
        processes.append((name, process))
        launched.append({"name": name, "pid": process.pid, "credential_name": key_name})
    atomic_json(score_root / "cloud_launch_manifest.json", {
        "version": "final197-qwen-single-readout-cloud-score-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "target_model": TARGET_MODEL,
        "evaluator_model": EVALUATOR_MODEL,
        "transport": "openai_batch_api",
        "merged_run": str(merged),
        "credentials_persisted": False,
        "jobs": launched,
    })
    print(json.dumps({"cloud_jobs": launched}, ensure_ascii=False), flush=True)
    if wait:
        codes = {name: process.wait() for name, process in processes}
        failures = {name: code for name, code in codes.items() if code}
        if failures:
            raise RuntimeError(f"cloud evaluation failed: {failures}")


def run_harmbench(
    merged: Path,
    score_root: Path,
    expected_cases: int,
    python: Path,
    classifier_model: str,
    batch_size: int,
    device: str,
) -> None:
    recovery = score_root / "recovery_behavior.json"
    if not recovery.is_file():
        raise FileNotFoundError(
            "recovery_behavior.json is required before HarmBench; finish --stage cloud --wait"
        )
    command = [
        str(python),
        "-m",
        "experiments.evaluate_harmbench_direct_response",
        "--run-dir",
        str(merged),
        "--recovery-evaluation",
        str(recovery),
        "--output",
        str(score_root / "harmbench.json"),
        "--classifier-model",
        classifier_model,
        "--batch-size",
        str(batch_size),
        "--device",
        device,
        "--expected-cases",
        str(expected_cases),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def summarize(score_root: Path, result_root: Path, arm: str) -> dict:
    cares_document = load(score_root / "cares_jmir" / "results.json")
    recovery_document = load(score_root / "recovery_behavior.json")
    harmbench_document = load(score_root / "harmbench.json")
    cares = cares_document["summary"]["best_of_4"]["cares"]
    jmir = cares_document["summary"]["best_of_4"]["jmir"]
    recovery = recovery_document["summary"]
    harmbench = harmbench_document["summary"]
    result = {
        "version": "final197-qwen-single-readout-combined-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_model": TARGET_MODEL,
        "evaluator_model": EVALUATOR_MODEL,
        "arm": arm,
        "method": "one_branch_local_research_readout_best_of_4",
        "cares_best_of_4": cares,
        "jmir_best_of_4": jmir,
        "recovery_behavior_best_of_4": recovery,
        "harmbench_and_same_branch_joint_best_of_4": harmbench,
    }
    atomic_json(score_root / "combined_summary.json", result)
    lines = [
        f"# Qwen Final-197 short readout · {arm}",
        "",
        "| 지표 | 결과 |",
        "|---|---:|",
        f"| CARES A/C/R/NR | {cares['A']}/{cares['C']}/{cares['R']}/{cares['NR']} |",
        f"| CARES Accept | {pct(cares['accept_rate'])} |",
        f"| CARES ASR | {pct(cares['cares_asr'])} |",
        f"| CARES SS ↓ | {cares['cares_ss_level2']:.3f} |",
        f"| JMIR mean ↓ | {jmir['mean_score']:.3f} |",
        f"| JMIR exact-1 | {pct(jmir['exact_1_harmful_rate'])} |",
        f"| R3+@4 | {pct(recovery['R3_plus_at_4'])} |",
        f"| B4+@4 | {pct(recovery['B4_plus_at_4'])} |",
        f"| HarmBench+@4 | {pct(harmbench['harmbench_unconditional_ASR_at_4'])} |",
        "| 같은 분기 R3+∧B4+∧HarmBench+@4 | "
        f"{pct(harmbench['joint_success_at_4'])} |",
        "",
    ]
    (result_root / "RESULTS_KO.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        action="append",
        choices=("merge", "cloud", "harmbench", "summary"),
        required=True,
    )
    parser.add_argument("--campaign-id", default=CAMPAIGN_ID)
    parser.add_argument("--arm", choices=ARMS, default="with_history")
    parser.add_argument("--campaign-root", type=Path)
    parser.add_argument("--result-root", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--lane-count", type=int, default=8)
    parser.add_argument("--expected-cases", type=int, default=197)
    parser.add_argument("--credential-name", default="OPENAI_API_KEY")
    parser.add_argument("--recovery-credential-name", default="OPENAI_API_KEY")
    parser.add_argument("--harmbench-python", type=Path, default=Path(sys.executable))
    parser.add_argument(
        "--harmbench-model",
        default="cais/HarmBench-Llama-2-13b-cls",
    )
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    campaign_root = (
        args.campaign_root.resolve() if args.campaign_root else
        ROOT / "data/evaluations" / args.campaign_id / "qwen2_5_7b" / args.arm
    )
    result_root = (
        args.result_root.resolve() if args.result_root else
        ROOT / "result/OURS" / args.campaign_id / "qwen2_5_7b" / args.arm
    )
    selection = (
        args.selection.resolve() if args.selection else
        campaign_root / "selection.json"
    )
    score_root = campaign_root / "scoring"
    stages = tuple(dict.fromkeys(args.stage))
    merged = result_root / "merged"
    if "merge" in stages or "cloud" in stages:
        merged, merge_summary = merge(
            result_root, args.lane_count, args.expected_cases
        )
        atomic_json(score_root / "merge_summary.json", merge_summary)
    if "cloud" in stages:
        launch_cloud(
            merged,
            selection,
            score_root,
            args.expected_cases,
            args.credential_name,
            args.recovery_credential_name,
            args.wait,
        )
    if "harmbench" in stages:
        run_harmbench(
            merged,
            score_root,
            args.expected_cases,
            args.harmbench_python.resolve(),
            args.harmbench_model,
            args.batch_size,
            args.device,
        )
    if "summary" in stages:
        print(json.dumps(
            summarize(score_root, result_root, args.arm),
            ensure_ascii=False,
            indent=2,
        ))


if __name__ == "__main__":
    main()

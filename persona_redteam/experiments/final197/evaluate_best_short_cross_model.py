#!/usr/bin/env python3
"""Merge and evaluate a best-short cross-model Final-197 run."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential
from experiments.final197.launch_best_short_cross_model import TARGETS
from experiments.merge_run_shards import merge_shards
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
GPU_PYTHON = Path("/data1/users/ljk98/envs/VLLM-VL-LABEL/bin/python")
HARMBENCH_MODEL = Path(
    "/data1/users/ljk98/hf_cache/hub/models--cais--HarmBench-Llama-2-13b-cls/"
    "snapshots/bda705349d1144fa618770bea64d99ce54e3835b"
)
SELECTION = (
    ROOT / "data/evaluations/final197_1011_singleton_gpt4o_v1/"
    "gpt4o/no_verbatim/selection.json"
)


def roots(campaign_id: str, target: str) -> tuple[Path, Path, Path, Path]:
    cohort = "cases_0_197"
    campaign = ROOT / "data/evaluations" / campaign_id / target / cohort
    result = ROOT / "result/OURS" / campaign_id / target / cohort
    return campaign, result, result / "merged", campaign / "scoring"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def merge(campaign_id: str, target: str) -> Path:
    campaign, result, merged, _ = roots(campaign_id, target)
    manifest = load(campaign / "launch_manifest.json")
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise RuntimeError("launch manifest does not contain any lane jobs")
    lane_numbers = sorted(int(job["lane"]) for job in jobs)
    if lane_numbers != list(range(len(lane_numbers))):
        raise RuntimeError(f"launch manifest has non-contiguous lanes: {lane_numbers}")
    lane_dirs = [result / f"lane_{index}" for index in lane_numbers]
    missing = [path / "run_summary.json" for path in lane_dirs
               if not (path / "run_summary.json").is_file()]
    if missing:
        raise RuntimeError(f"generation has {len(missing)} incomplete lanes")
    merge_shards(lane_dirs, merged, 197)
    return merged


def run_logged(command: list[str], log: Path, environment: dict[str, str]):
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("ab", buffering=0)
    process = subprocess.Popen(
        command, cwd=ROOT, env=environment,
        stdout=handle, stderr=subprocess.STDOUT,
    )
    handle.close()
    return process


def launch_cloud(campaign_id: str, target: str, wait: bool) -> None:
    campaign, _, merged, scoring = roots(campaign_id, target)
    scoring.mkdir(parents=True, exist_ok=True)
    target_model = str(TARGETS[target]["model"])
    environment = os.environ.copy()
    environment["OPENAI_API_KEY"] = credential("OPENAI_API_KEY")
    jobs = []
    cares = scoring / "cares_jmir/results.json"
    if not cares.is_file():
        command = [
            sys.executable, "-m", "experiments.evaluate_final_cares_pilot64",
            "--run-dir", str(merged), "--selection", str(SELECTION),
            "--output-dir", str(scoring / "cares_jmir"),
            "--api-mode", "batch", "--evaluator-model", "gpt-4o-2024-11-20",
            "--expected-cases", "197", "--target-model", target_model,
            "--workers", "128", "--max-budget-usd", "60",
            "--poll-seconds", "20", "--execute",
        ]
        jobs.append(("cares_jmir", run_logged(
            command, scoring / "cares_jmir.log", environment
        )))
    recovery = scoring / "recovery_behavior.json"
    if not recovery.is_file():
        command = [
            sys.executable, "-m", "experiments.evaluate_recovery_behavior_batch",
            "--run-dir", str(merged), "--output", str(recovery),
            "--model", "gpt-4o-2024-11-20", "--expected-cases", "197",
            "--api-mode", "batch", "--workers", "128",
            "--max-budget-usd", "60", "--poll-seconds", "20", "--execute",
        ]
        jobs.append(("recovery_behavior", run_logged(
            command, scoring / "recovery_behavior.log", environment
        )))
    atomic_json(scoring / "cloud_launch_manifest.json", {
        "version": "best-short-cross-model-scoring-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "target_model": target_model,
        "evaluator_model": "gpt-4o-2024-11-20",
        "api_mode": "openai_batch",
        "credentials_persisted": False,
        "jobs": [{"name": name, "pid": process.pid} for name, process in jobs],
    })
    if wait:
        failures = {name: process.wait() for name, process in jobs}
        failures = {name: code for name, code in failures.items() if code}
        if failures:
            raise RuntimeError(f"cloud evaluation failed: {failures}")


def run_harmbench(campaign_id: str, target: str, device: str) -> None:
    _, _, merged, scoring = roots(campaign_id, target)
    recovery = scoring / "recovery_behavior.json"
    if not recovery.is_file():
        raise FileNotFoundError("recovery/behavior Batch evaluation is incomplete")
    output = scoring / "harmbench.json"
    if output.is_file():
        return
    command = [
        str(GPU_PYTHON), "-m", "experiments.evaluate_harmbench_direct_response",
        "--run-dir", str(merged), "--recovery-evaluation", str(recovery),
        "--output", str(output), "--classifier-model", str(HARMBENCH_MODEL),
        "--batch-size", "32", "--device", device, "--expected-cases", "197",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def summarize(campaign_id: str, target: str) -> dict:
    _, result, _, scoring = roots(campaign_id, target)
    cares_doc = load(scoring / "cares_jmir/results.json")
    recovery_doc = load(scoring / "recovery_behavior.json")
    harm_doc = load(scoring / "harmbench.json")
    cares = cares_doc["summary"]["best_of_4"]["cares"]
    jmir = cares_doc["summary"]["best_of_4"]["jmir"]
    recovery = recovery_doc["summary"]
    harm = harm_doc["summary"]
    record = {
        "version": "best-short-cross-model-summary-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "target_model": TARGETS[target]["model"],
        "method": "with_history_plus_one_branch_local_research_readout",
        "cases": 197,
        "branches": 788,
        "cares_best_of_4": cares,
        "jmir_best_of_4": jmir,
        "recovery_behavior_best_of_4": recovery,
        "harmbench_and_joint_best_of_4": harm,
        "evaluator_model": "gpt-4o-2024-11-20",
    }
    atomic_json(scoring / "combined_summary.json", record)
    lines = [
        f"# {TARGETS[target]['model']} · Final-197 best short readout", "",
        "- 방법: 페르소나 이력 + fresh target initial analysis + 분기별 연구 readout 1회",
        "- 표본: 197건 × 독립 최종 분기 4개, 사례별 Best-of-4",
        "- CARES/JMIR/R/B 평가자: GPT-4o (`gpt-4o-2024-11-20`)",
        "- HarmBench: 공식 로컬 분류기", "",
        "| 지표 | 결과 |", "|---|---:|",
        f"| CARES A/C/R/NR | {cares['A']}/{cares['C']}/{cares['R']}/{cares['NR']} |",
        f"| CARES Accept | {pct(cares['accept_rate'])} |",
        f"| CARES ASR | {pct(cares['cares_asr'])} |",
        f"| CARES SS ↓ | {cares['cares_ss_level2']:.3f} |",
        f"| JMIR mean ↓ | {jmir['mean_score']:.3f} |",
        f"| JMIR exact-1 | {pct(jmir['exact_1_harmful_rate'])} |",
        f"| R3+@4 | {pct(recovery['R3_plus_at_4'])} |",
        f"| B4+@4 | {pct(recovery['B4_plus_at_4'])} |",
        f"| HarmBench+@4 | {pct(harm['harmbench_unconditional_ASR_at_4'])} |",
        f"| 같은 분기 R3+∧B4+∧HarmBench+@4 | {pct(harm['joint_success_at_4'])} |",
        "",
        "결합 지표는 서로 다른 분기의 최댓값을 섞지 않고 같은 분기에서 세 조건을 모두 만족한 사례만 센다.",
        "",
    ]
    (result / "RESULTS_KO.md").write_text("\n".join(lines), encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--campaign-id", default="final197_best_short_cross_model_v1")
    parser.add_argument("--stage", action="append",
                        choices=("merge", "cloud", "harmbench", "summary"),
                        required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    stages = tuple(dict.fromkeys(args.stage))
    if "merge" in stages or "cloud" in stages:
        merge(args.campaign_id, args.target)
    if "cloud" in stages:
        launch_cloud(args.campaign_id, args.target, args.wait)
    if "harmbench" in stages:
        run_harmbench(args.campaign_id, args.target, args.device)
    if "summary" in stages:
        print(json.dumps(summarize(args.campaign_id, args.target),
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

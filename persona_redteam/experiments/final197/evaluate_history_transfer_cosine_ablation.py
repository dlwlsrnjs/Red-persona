#!/usr/bin/env python3
"""Merge, score, and summarize one cosine history-transfer cell."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

from experiments.final197.credentials import credential
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
ARMS = ("matched", "mismatched")
HORIZONS = ("short", "long")


def roots(campaign_id: str, arm: str, horizon: str, cohort: str):
    campaign = (
        ROOT / "data/evaluations" / campaign_id / "gpt4o" /
        arm / horizon / cohort
    )
    result = (
        ROOT / "result/OURS" / campaign_id / "gpt4o" /
        arm / horizon / cohort
    )
    return campaign, result, result / "merged", campaign / "scoring"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def artifacts(merged: Path) -> list[dict]:
    return [
        load(path) for path in sorted(merged.glob("*.json"))
        if path.name != "run_summary.json"
    ]


def cohort_selection(merged: Path, scoring: Path, expected: int) -> Path:
    """Return a selection containing exactly the generated cohort.

    The canonical selection contains all 197 cases, while a pilot contains ten.
    The shared CARES evaluator intentionally requires an exact-size selection,
    so materialize a cohort-local view in canonical order for partial runs.
    """
    canonical = load(SELECTION)
    canonical_ids = [str(value) for value in canonical.get("case_ids", [])]
    generated_ids = {
        str(record.get("case", {}).get("case_id")) for record in artifacts(merged)
    }
    selected = [case_id for case_id in canonical_ids if case_id in generated_ids]
    if len(selected) != expected or len(generated_ids) != expected:
        raise RuntimeError(
            f"cohort selection mismatch: expected={expected}, "
            f"generated={len(generated_ids)}, canonical_intersection={len(selected)}"
        )
    output = scoring / "cohort_selection.json"
    atomic_json(output, {
        "version": "history-transfer-cohort-selection-v1",
        "expected_cases": expected,
        "case_ids": selected,
    })
    return output


def merge(campaign_id: str, arm: str, horizon: str, cohort: str,
          expected: int) -> Path:
    campaign, result, merged, _ = roots(campaign_id, arm, horizon, cohort)
    manifest = load(campaign / "launch_manifest.json")
    lane_dirs = [result / f"lane_{job_index}" for job_index, _ in enumerate(
        manifest.get("jobs", [])
    )]
    missing = [path / "run_summary.json" for path in lane_dirs
               if not (path / "run_summary.json").is_file()]
    if missing:
        raise RuntimeError(f"generation has {len(missing)} incomplete lanes")
    merge_shards(lane_dirs, merged, expected)
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


def launch_cloud(campaign_id: str, arm: str, horizon: str, cohort: str,
                 expected: int, wait: bool) -> None:
    campaign, _, merged, scoring = roots(campaign_id, arm, horizon, cohort)
    scoring.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["OPENAI_API_KEY"] = credential("OPENAI_API_KEY")
    selection = cohort_selection(merged, scoring, expected)
    jobs = []
    cares = scoring / "cares_jmir/results.json"
    if not cares.is_file():
        command = [
            sys.executable, "-m", "experiments.evaluate_final_cares_pilot64",
            "--run-dir", str(merged), "--selection", str(selection),
            "--output-dir", str(scoring / "cares_jmir"),
            "--api-mode", "batch", "--evaluator-model", "gpt-4o-2024-11-20",
            "--expected-cases", str(expected),
            "--target-model", "gpt-4o-2024-11-20",
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
            "--model", "gpt-4o-2024-11-20",
            "--expected-cases", str(expected), "--api-mode", "batch",
            "--workers", "128", "--max-budget-usd", "60",
            "--poll-seconds", "20", "--execute",
        ]
        jobs.append(("recovery_behavior", run_logged(
            command, scoring / "recovery_behavior.log", environment
        )))
    atomic_json(scoring / "cloud_launch_manifest.json", {
        "version": "history-transfer-cosine-scoring-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "arm": arm, "horizon": horizon, "cohort": cohort,
        "target_model": "gpt-4o-2024-11-20",
        "evaluator_model": "gpt-4o-2024-11-20",
        "api_mode": "openai_batch", "credentials_persisted": False,
        "jobs": [{"name": name, "pid": process.pid} for name, process in jobs],
    })
    if wait:
        failures = {name: process.wait() for name, process in jobs}
        failures = {name: code for name, code in failures.items() if code}
        if failures:
            raise RuntimeError(f"cloud evaluation failed: {failures}")


def run_harmbench(campaign_id: str, arm: str, horizon: str, cohort: str,
                  expected: int, device: str) -> None:
    _, _, merged, scoring = roots(campaign_id, arm, horizon, cohort)
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
        "--batch-size", "32", "--device", device,
        "--expected-cases", str(expected),
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def turn_summary(merged: Path, case_ids: set[str] | None = None) -> dict:
    rows = []
    for record in artifacts(merged):
        record_case_id = str(record.get("case", {}).get("case_id", ""))
        if case_ids is not None and record_case_id not in case_ids:
            continue
        result = record["results"][0]
        turns = result.get("turns", [])
        stages = [turn.get("stage") for turn in turns]
        branches = result.get("final_branches", [])
        readouts = sum(bool(branch.get("recovery_response")) for branch in branches)
        direct = sum(bool(branch.get("attack_response")) for branch in branches)
        available = sum(
            branch.get("bridge_record", {}).get("status") == "available"
            for branch in branches
        )
        case = record.get("case", {})
        transfer = case.get("history_transfer", {})
        cosine = transfer.get("cosine")
        rows.append({
            "case_id": case["case_id"],
            "cosine": None if cosine is None else float(cosine),
            "prehistory_turns": int(transfer.get(
                "donor_history_turns", len(case.get("persona_history", []))
            )),
            "shared_research_turns": sum(stage != "initial_analysis" for stage in stages),
            "case_ab_recovery_turns": sum(
                str(stage).startswith("case_ab_goal_recovery") for stage in stages
            ),
            "reached_latent_goal": "latent_goal" in stages,
            "branch_readout_turns": readouts,
            "direct_response_turns": direct,
            "available_quote_branches": available,
            "any_quote_available": available > 0,
            "total_target_completions": len(turns) + readouts + direct,
        })
    return {
        "cases": len(rows),
        "mean_cosine": mean([
            row["cosine"] for row in rows if row["cosine"] is not None
        ]),
        "mean_prehistory_turns": mean([row["prehistory_turns"] for row in rows]),
        "mean_shared_research_turns": mean([
            row["shared_research_turns"] for row in rows
        ]),
        "mean_case_ab_recovery_turns": mean([
            row["case_ab_recovery_turns"] for row in rows
        ]),
        "latent_goal_reached_rate": mean([
            row["reached_latent_goal"] for row in rows
        ]),
        "mean_branch_readout_turns": mean([
            row["branch_readout_turns"] for row in rows
        ]),
        "mean_direct_response_turns": mean([
            row["direct_response_turns"] for row in rows
        ]),
        "mean_total_target_completions": mean([
            row["total_target_completions"] for row in rows
        ]),
        "quote_available_case_rate": mean([
            row["any_quote_available"] for row in rows
        ]),
        "quote_available_branch_rate": (
            sum(row["available_quote_branches"] for row in rows)
            / (4 * len(rows)) if rows else 0.0
        ),
        "rows": rows,
    }


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def summarize(campaign_id: str, arm: str, horizon: str, cohort: str) -> dict:
    _, result_root, merged, scoring = roots(campaign_id, arm, horizon, cohort)
    cares_doc = load(scoring / "cares_jmir/results.json")
    recovery_doc = load(scoring / "recovery_behavior.json")
    harm_doc = load(scoring / "harmbench.json")
    cares = cares_doc["summary"]["best_of_4"]["cares"]
    jmir = cares_doc["summary"]["best_of_4"]["jmir"]
    recovery = recovery_doc["summary"]
    harm = harm_doc["summary"]
    turns = turn_summary(merged)
    record = {
        "version": "history-transfer-cosine-summary-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "arm": arm, "research_horizon": horizon, "cohort": cohort,
        "target_model": "gpt-4o-2024-11-20",
        "cases": turns["cases"], "branches": turns["cases"] * 4,
        "cares_best_of_4": cares,
        "jmir_best_of_4": jmir,
        "recovery_behavior_best_of_4": recovery,
        "harmbench_and_joint_best_of_4": harm,
        "turns_and_goal_recovery": turns,
        "evaluator_model": "gpt-4o-2024-11-20",
    }
    atomic_json(scoring / "combined_summary.json", record)
    lines = [
        f"# History transfer: {arm} × {horizon} ({cohort})", "",
        "- 타깃: GPT-4o (`gpt-4o-2024-11-20`)",
        "- 평가: GPT-4o CARES/JMIR/R/B + 공식 로컬 HarmBench",
        "- 결합 지표는 같은 분기에서 세 조건을 동시에 만족한 경우만 집계", "",
        "| 지표 | 결과 |", "|---|---:|",
        f"| 사례 / 분기 | {record['cases']} / {record['branches']} |",
        f"| donor cosine 평균 | {turns['mean_cosine']:.4f} |",
        f"| 사전 이력 턴 평균 | {turns['mean_prehistory_turns']:.2f} |",
        f"| 공유 연구 턴 평균 | {turns['mean_shared_research_turns']:.2f} |",
        f"| 전체 타깃 completion 평균 | {turns['mean_total_target_completions']:.2f} |",
        f"| latent_goal 도달 | {pct(turns['latent_goal_reached_rate'])} |",
        f"| 인용 가능 사례 | {pct(turns['quote_available_case_rate'])} |",
        f"| CARES A/C/R/NR | {cares['A']}/{cares['C']}/{cares['R']}/{cares['NR']} |",
        f"| CARES Accept | {pct(cares['accept_rate'])} |",
        f"| CARES ASR | {pct(cares['cares_asr'])} |",
        f"| CARES SS ↓ | {cares['cares_ss_level2']:.3f} |",
        f"| JMIR mean ↓ | {jmir['mean_score']:.3f} |",
        f"| R3+@4 | {pct(recovery['R3_plus_at_4'])} |",
        f"| B4+@4 | {pct(recovery['B4_plus_at_4'])} |",
        f"| HarmBench+@4 | {pct(harm['harmbench_unconditional_ASR_at_4'])} |",
        f"| R3+∧B4+∧HarmBench+@4 | {pct(harm['joint_success_at_4'])} |",
        "",
    ]
    (result_root / "RESULTS_KO.md").write_text("\n".join(lines), encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--horizon", choices=HORIZONS, required=True)
    parser.add_argument("--campaign-id", default="final197_history_transfer_cosine_v1")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--stage", action="append",
                        choices=("merge", "cloud", "harmbench", "summary"),
                        required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    cohort = "pilot10" if args.pilot else "cases_0_197"
    expected = 10 if args.pilot else 197
    stages = tuple(dict.fromkeys(args.stage))
    if "merge" in stages or "cloud" in stages:
        merge(args.campaign_id, args.arm, args.horizon, cohort, expected)
    if "cloud" in stages:
        launch_cloud(
            args.campaign_id, args.arm, args.horizon, cohort, expected, args.wait
        )
    if "harmbench" in stages:
        run_harmbench(
            args.campaign_id, args.arm, args.horizon, cohort, expected, args.device
        )
    if "summary" in stages:
        print(json.dumps(summarize(
            args.campaign_id, args.arm, args.horizon, cohort
        ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

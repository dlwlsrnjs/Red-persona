#!/usr/bin/env python3
"""Launch the registered best Final-197 short-readout method on new targets.

The historical CLI name ``no-research-dialogue`` means that the seven-stage
accumulation is disabled.  It still performs one branch-local research readout
in each of the four final directions before the contiguous response measure.
Every target gets a fresh target-authored initial analysis; GPT-4o checkpoints
are deliberately not reused across models.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential
from experiments.final197.prepare_full197_experiment_matrix import ARM_PATHS
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
QWEN_MODEL = "Qwen/Qwen2.5-7B-Instruct"
QWEN_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
RESEARCHER_URLS = (
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1",
    "http://127.0.0.1:8022/v1",
)
TARGETS = {
    "gpt5_4_mini": {
        "model": "gpt-5.4-mini",
        "transport": "openai_batch",
    },
    "gpt6_luna": {
        "model": "gpt-6-luna",
        "transport": "openai_batch",
    },
    "llama3_g2c": {
        "model": "UKPLab/Llama3-G2C",
        "transport": "local_vllm",
    },
    "llama3_1_8b_instruct": {
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "transport": "local_vllm",
    },
    "gemma4_26b_a4b_it": {
        "model": "google/gemma-4-26B-A4B-it",
        "transport": "local_vllm",
    },
    "mistral_small_3_2_24b": {
        "model": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
        "transport": "local_vllm",
    },
    "phi4": {
        "model": "microsoft/phi-4",
        "transport": "local_vllm",
    },
}


def canonical_selection() -> Path:
    return (
        ROOT / "data/evaluations/final197_1011_singleton_gpt4o_v1/"
        "gpt4o/no_verbatim/selection.json"
    )


def ranges(start: int, stop: int, lanes: int) -> list[tuple[int, int]]:
    total = stop - start
    lanes = max(1, min(lanes, total))
    base, remainder = divmod(total, lanes)
    result = []
    cursor = start
    for lane in range(lanes):
        width = base + (1 if lane < remainder else 0)
        result.append((cursor, cursor + width))
        cursor += width
    return result


def base_command(target: str, campaign: Path, result: Path) -> list[str]:
    spec = TARGETS[target]
    return [
        sys.executable, "-m", "experiments.run_jmir_persona_batch_api",
        "--cases", str(ARM_PATHS["no_verbatim"]),
        "--selection-path", str(canonical_selection()),
        "--selection-key", "case_ids",
        "--condition", "neutral",
        "--final-readout-protocol", "safety_negative_examples_v1",
        "--direct-response-prompt-protocol", "counterfactual_prevention_v1",
        "--research-language-profile", "clinical_safety_terminology_v1",
        "--require-strict-harmful-goal-v3",
        "--target-total", "197",
        "--target-workers", "128",
        "--researcher-workers", "32",
        "--max-budget-usd", "40",
        "--poll-seconds", "20",
        "--max-goal-convergence-turns", "0",
        "--method-protocol", "1011_method_v1",
        "--target-model", str(spec["model"]),
        "--researcher-model", QWEN_MODEL,
        "--researcher-revision", QWEN_REVISION,
        "--campaign-dir", str(campaign),
        "--output-dir", str(campaign / "unused_long_dialogue_output"),
        "--no-research-dialogue-output-dir", str(result),
        "--only-no-research-dialogue",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--campaign-id", default="final197_best_short_cross_model_v1")
    parser.add_argument("--pilot", action="store_true",
                        help="Run the preregistered first ten cases only.")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--lanes", type=int)
    parser.add_argument("--target-base-url", action="append", default=[])
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    spec = TARGETS[args.target]
    stop = 10 if args.pilot else (args.stop if args.stop is not None else 197)
    start = args.start
    if not 0 <= start < stop <= 197:
        parser.error("require 0 <= start < stop <= 197")
    default_lanes = 1 if args.pilot else (
        8 if spec["transport"] == "openai_batch" else
        max(1, len(args.target_base_url))
    )
    lane_count = args.lanes or default_lanes
    slices = ranges(start, stop, lane_count)
    if spec["transport"] == "local_vllm" and not args.target_base_url:
        parser.error("local targets require at least one --target-base-url")

    cohort = "pilot10" if args.pilot else f"cases_{start}_{stop}"
    campaign_root = ROOT / "data/evaluations" / args.campaign_id / args.target / cohort
    result_root = ROOT / "result/OURS" / args.campaign_id / args.target / cohort
    campaign_root.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)

    selection = json.loads(canonical_selection().read_text(encoding="utf-8"))
    if len(selection.get("case_ids", [])) != 197:
        raise RuntimeError("canonical Final-197 selection is incomplete")

    # Contract check does not initialize a model or submit an API request.
    check_command = [
        *base_command(args.target, campaign_root / "prepare", result_root / "prepare"),
        "--start", str(start), "--stop", str(stop), "--prepare-only",
    ]
    completed = subprocess.run(check_command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    if args.prepare_only:
        return

    environment = os.environ.copy()
    if spec["transport"] == "openai_batch":
        environment["OPENAI_API_KEY"] = credential("OPENAI_API_KEY")

    processes: list[tuple[str, subprocess.Popen]] = []
    jobs = []
    for lane, (lane_start, lane_stop) in enumerate(slices):
        campaign = campaign_root / f"lane_{lane}"
        result = result_root / f"lane_{lane}"
        command = [
            *base_command(args.target, campaign, result),
            "--researcher-base-url", RESEARCHER_URLS[lane % len(RESEARCHER_URLS)],
            "--start", str(lane_start), "--stop", str(lane_stop),
        ]
        target_url = None
        if spec["transport"] == "local_vllm":
            target_url = args.target_base_url[lane % len(args.target_base_url)]
            command.extend(("--target-base-url", target_url))
        else:
            command.extend(("--api-mode", "batch"))
        log_path = campaign_root / f"lane_{lane}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=not args.wait,
        )
        log_handle.close()
        processes.append((f"lane_{lane}", process))
        jobs.append({
            "lane": lane,
            "pid": process.pid,
            "start": lane_start,
            "stop": lane_stop,
            "researcher_base_url": RESEARCHER_URLS[lane % len(RESEARCHER_URLS)],
            "target_base_url": target_url,
            "log": str(log_path),
        })

    manifest = {
        "version": "final197-best-short-cross-model-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "campaign_id": args.campaign_id,
        "cohort": cohort,
        "target_key": args.target,
        "target_model": spec["model"],
        "transport": spec["transport"],
        "method": "with_history_plus_one_branch_local_research_readout",
        "long_seven_stage_dialogue": False,
        "fresh_target_initial_analysis": True,
        "gpt4o_initial_reuse": False,
        "final_branches": 4,
        "credentials_persisted": False,
        "jobs": jobs,
    }
    atomic_json(campaign_root / "launch_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)

    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print(json.dumps({"return_codes": return_codes}, ensure_ascii=False), flush=True)
        failures = {name: code for name, code in return_codes.items() if code}
        if failures:
            raise SystemExit(max(failures.values()))
        # The legacy runner's field name assumes that every short-horizon run
        # reused an earlier GPT-4o initial analysis.  Cross-model runs never do:
        # each target generated its own initial analysis above.  Normalize this
        # metadata at the isolated launcher boundary without changing old runs.
        for lane in range(len(slices)):
            summary_path = result_root / f"lane_{lane}" / "run_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            base_mode = str(summary.get("api_mode", spec["transport"])).split("_reusing", 1)[0]
            summary["api_mode"] = base_mode + "_fresh_initial_analysis"
            summary["fresh_target_initial_analysis"] = True
            summary["reused_initial_analysis"] = False
            atomic_json(summary_path, summary)


if __name__ == "__main__":
    main()

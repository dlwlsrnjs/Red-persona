#!/usr/bin/env python3
"""Launch the portable Final-197 Qwen short-readout experiment.

The Qwen target and the independent Llama researcher are served through local
OpenAI-compatible endpoints (normally vLLM).  The historical runner option
``--only-no-research-dialogue`` removes the seven accumulated research stages;
it still retains one branch-local research readout in each of four directions.
GPT-4o Batch judging is performed later by ``finalize_single_readout_qwen.py``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.runtime_io import atomic_json


CAMPAIGN_ID = "final197_single_readout_qwen_v2"
ARMS = ("with_history", "no_history")
QWEN_MODEL = "Qwen/Qwen2.5-7B-Instruct"
QWEN_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
LLAMA_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
LLAMA_REVISION = "0e9e39f249a16976918f6564b8830bc894c89659"
DEFAULT_CASES = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "contrastive_goal_question_pool_gpt4o_v5_fixed_comparison/"
    "persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json"
)
DEFAULT_TARGET_URLS = (
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1",
    "http://127.0.0.1:8022/v1",
)
DEFAULT_RESEARCHER_URLS = (
    "http://127.0.0.1:8100/v1",
    "http://127.0.0.1:8101/v1",
    "http://127.0.0.1:8102/v1",
    "http://127.0.0.1:8103/v1",
)
PROMPT_SOURCES = (
    ROOT / "experiments/qwen_target_persona_research_dialogue.py",
    ROOT / "evaluation/prompts/behavioral_risk_case_research_guidelines.md",
    ROOT / "evaluation/prompts/research_prompt_banks_en.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ranges(start: int, stop: int, lanes: int) -> list[tuple[int, int]]:
    total = stop - start
    if lanes < 1 or lanes > total:
        raise ValueError("lanes must be between 1 and the selected case count")
    width, remainder = divmod(total, lanes)
    result = []
    cursor = start
    for lane in range(lanes):
        size = width + (1 if lane < remainder else 0)
        result.append((cursor, cursor + size))
        cursor += size
    return result


def validate_cases(path: Path, expected_cases: int) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("--cases must contain one JSON array")
    ids = [str(row.get("case_id", "")) for row in value]
    if len(ids) != expected_cases or len(set(ids)) != expected_cases:
        raise ValueError(
            f"--cases must contain exactly {expected_cases} unique case IDs"
        )
    missing = [
        case_id for case_id, row in zip(ids, value)
        if not str(row.get("original_request", "")).strip()
        or not str(row.get("persona", "")).strip()
        or not isinstance(row.get("similar_goal_question_pool"), dict)
    ]
    if missing:
        raise ValueError(
            "cases are missing the GOAL/persona/Case-A-B contract: "
            + ", ".join(missing[:5])
        )


def validate_selection(path: Path, expected_cases: int) -> None:
    if not path.exists():
        return
    value = json.loads(path.read_text(encoding="utf-8"))
    ids = value.get("case_ids", [])
    if (
        value.get("target_total") != expected_cases
        or len(ids) != expected_cases
        or len(set(map(str, ids))) != expected_cases
    ):
        raise ValueError(
            f"--selection-path must identify {expected_cases} unique cases"
        )


def base_command(
    args: argparse.Namespace,
    campaign: Path,
    result: Path,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "experiments.run_jmir_persona_batch_api",
        "--cases",
        str(args.cases),
        "--selection-path",
        str(args.selection_path),
        "--selection-key",
        "case_ids",
        "--condition",
        "neutral",
        "--final-readout-protocol",
        "safety_negative_examples_v1",
        "--direct-response-prompt-protocol",
        "counterfactual_prevention_v1",
        "--research-language-profile",
        "clinical_safety_terminology_v1",
        "--require-strict-harmful-goal-v3",
        "--target-total",
        str(args.expected_cases),
        "--target-workers",
        str(args.target_workers),
        "--researcher-workers",
        str(args.researcher_workers),
        "--max-budget-usd",
        "1",
        "--poll-seconds",
        "20",
        "--max-goal-convergence-turns",
        "0",
        "--method-protocol",
        "1011_method_v1",
        "--target-model",
        QWEN_MODEL,
        "--researcher-model",
        LLAMA_MODEL,
        "--researcher-revision",
        LLAMA_REVISION,
        "--campaign-dir",
        str(campaign),
        "--output-dir",
        str(campaign / "unused_seven_stage_output"),
        "--no-research-dialogue-output-dir",
        str(result),
        "--only-no-research-dialogue",
    ]
    if args.arm == "no_history":
        command.extend(("--ablation-variant", "no_prior_dialogue"))
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--selection-path", type=Path)
    parser.add_argument("--campaign-root", type=Path)
    parser.add_argument("--result-root", type=Path)
    parser.add_argument("--campaign-id", default=CAMPAIGN_ID)
    parser.add_argument("--arm", choices=ARMS, default="with_history")
    parser.add_argument("--expected-cases", type=int, default=197)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--lanes", type=int, default=8)
    parser.add_argument("--only-lane", type=int)
    parser.add_argument("--target-base-url", action="append", default=[])
    parser.add_argument("--researcher-base-url", action="append", default=[])
    parser.add_argument("--target-workers", type=int, default=128)
    parser.add_argument("--researcher-workers", type=int, default=32)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    args.cases = args.cases.resolve()
    stop = args.stop if args.stop is not None else args.expected_cases
    if not 0 <= args.start < stop <= args.expected_cases:
        parser.error("require 0 <= --start < --stop <= --expected-cases")
    if args.target_workers < 1 or args.researcher_workers < 1:
        parser.error("worker counts must be positive")
    try:
        slices = ranges(args.start, stop, args.lanes)
        validate_cases(args.cases, args.expected_cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if args.only_lane is not None and not 0 <= args.only_lane < len(slices):
        parser.error("--only-lane is outside the configured lane range")

    base_campaign_root = (
        args.campaign_root.resolve() if args.campaign_root else
        ROOT / "data/evaluations" / args.campaign_id / "qwen2_5_7b" / args.arm
    )
    base_result_root = (
        args.result_root.resolve() if args.result_root else
        ROOT / "result/OURS" / args.campaign_id / "qwen2_5_7b" / args.arm
    )
    args.selection_path = (
        args.selection_path.resolve() if args.selection_path else
        base_campaign_root / "selection.json"
    )
    base_campaign_root.mkdir(parents=True, exist_ok=True)
    base_result_root.mkdir(parents=True, exist_ok=True)
    args.selection_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_selection(args.selection_path, args.expected_cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    target_urls = tuple(args.target_base_url) or DEFAULT_TARGET_URLS
    researcher_urls = tuple(args.researcher_base_url) or DEFAULT_RESEARCHER_URLS

    prepared = subprocess.run(
        [
            *base_command(
                args,
                base_campaign_root / "prepare",
                base_result_root / "prepare",
            ),
            "--prepare-only",
        ],
        cwd=ROOT,
        check=False,
    )
    if prepared.returncode:
        raise SystemExit(prepared.returncode)
    validate_selection(args.selection_path, args.expected_cases)
    if args.prepare_only:
        print(json.dumps({
            "status": "prepared",
            "cases": str(args.cases),
            "selection": str(args.selection_path),
            "cases_sha256": sha256(args.cases),
            "selection_sha256": sha256(args.selection_path),
        }, ensure_ascii=False, indent=2))
        return

    processes: list[tuple[str, subprocess.Popen]] = []
    jobs = []
    for lane, (lane_start, lane_stop) in enumerate(slices):
        if args.only_lane is not None and lane != args.only_lane:
            continue
        target_url = target_urls[lane % len(target_urls)]
        researcher_url = researcher_urls[lane % len(researcher_urls)]
        campaign = base_campaign_root / f"lane_{lane}"
        result = base_result_root / f"lane_{lane}"
        command = [
            *base_command(args, campaign, result),
            "--target-base-url",
            target_url,
            "--researcher-base-url",
            researcher_url,
            "--start",
            str(lane_start),
            "--stop",
            str(lane_stop),
        ]
        log_path = base_campaign_root / f"lane_{lane}.log"
        log_handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=not args.wait,
        )
        log_handle.close()
        name = f"lane_{lane}"
        processes.append((name, process))
        jobs.append({
            "lane": lane,
            "pid": process.pid,
            "start": lane_start,
            "stop": lane_stop,
            "target_base_url": target_url,
            "researcher_base_url": researcher_url,
            "log": str(log_path),
        })

    manifest = {
        "version": "final197-qwen-single-readout-portable-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "campaign_id": args.campaign_id,
        "arm": args.arm,
        "cases": str(args.cases),
        "cases_sha256": sha256(args.cases),
        "selection": str(args.selection_path),
        "selection_sha256": sha256(args.selection_path),
        "target_model": QWEN_MODEL,
        "target_revision": QWEN_REVISION,
        "researcher_model": LLAMA_MODEL,
        "researcher_revision": LLAMA_REVISION,
        "method_protocol": "1011_method_v1",
        "research_horizon": "one_branch_local_readout",
        "seven_stage_research_dialogue": False,
        "final_branches": 4,
        "persona_prehistory": args.arm,
        "target_transport": "local_vllm_openai_compatible_continuous_batching",
        "judge_transport": "openai_batch_api_after_generation",
        "prompt_sources": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
            for path in PROMPT_SOURCES
        ],
        "credentials_persisted": False,
        "jobs": jobs,
    }
    atomic_json(base_campaign_root / "launch_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)

    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print(json.dumps({
            "status": "all_generation_jobs_exited",
            "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failures = {name: code for name, code in return_codes.items() if code}
        if failures:
            raise SystemExit(max(failures.values()))


if __name__ == "__main__":
    main()

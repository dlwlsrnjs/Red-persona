#!/usr/bin/env python3
"""Launch the Final-197 cosine history-transfer factorial on GPT-4o."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "history_transfer_cosine_v1"
)
CASES = {
    "matched": DATA_ROOT / "persona_cases_MATCHED_HISTORY.json",
    "mismatched": DATA_ROOT / "persona_cases_MISMATCHED_HISTORY.json",
}
HORIZONS = ("short", "long")
QWEN_MODEL = "Qwen/Qwen2.5-7B-Instruct"
QWEN_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
RESEARCHER_URLS = (
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1",
    "http://127.0.0.1:8022/v1",
)


def canonical_selection() -> Path:
    return (
        ROOT / "data/evaluations/final197_1011_singleton_gpt4o_v1/"
        "gpt4o/no_verbatim/selection.json"
    )


def slices(start: int, stop: int, lanes: int) -> list[tuple[int, int]]:
    lanes = max(1, min(lanes, stop - start))
    base, remainder = divmod(stop - start, lanes)
    result = []
    cursor = start
    for lane in range(lanes):
        width = base + (1 if lane < remainder else 0)
        result.append((cursor, cursor + width))
        cursor += width
    return result


def base_command(arm: str, horizon: str, campaign: Path,
                 result: Path) -> list[str]:
    command = [
        sys.executable, "-m", "experiments.run_jmir_persona_batch_api",
        "--cases", str(CASES[arm]),
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
        "--max-budget-usd", "60",
        "--poll-seconds", "20",
        "--max-goal-convergence-turns", "0",
        "--method-protocol", "1011_method_v1",
        "--target-model", "gpt-4o-2024-11-20",
        "--researcher-model", QWEN_MODEL,
        "--researcher-revision", QWEN_REVISION,
        "--api-mode", "batch",
        "--campaign-dir", str(campaign),
    ]
    if horizon == "short":
        command.extend((
            "--output-dir", str(campaign / "unused_long_dialogue_output"),
            "--no-research-dialogue-output-dir", str(result),
            "--only-no-research-dialogue",
        ))
    else:
        command.extend(("--output-dir", str(result)))
    return command


def validate_inputs() -> None:
    mapping = json.loads(
        (DATA_ROOT / "history_transfer_mapping.json").read_text(encoding="utf-8")
    )
    if len(mapping) != 197:
        raise ValueError("history-transfer mapping must contain 197 cases")
    for arm, path in CASES.items():
        rows = json.loads(path.read_text(encoding="utf-8"))
        if len(rows) != 197 or len({row["case_id"] for row in rows}) != 197:
            raise ValueError(f"{arm}: expected 197 unique cases")
        if any(row.get("history_transfer", {}).get("mode") != arm for row in rows):
            raise ValueError(f"{arm}: transfer metadata mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="append", choices=CASES)
    parser.add_argument("--horizon", action="append", choices=HORIZONS)
    parser.add_argument("--campaign-id", default="final197_history_transfer_cosine_v1")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--lanes", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    validate_inputs()
    arms = tuple(dict.fromkeys(args.arm or CASES))
    horizons = tuple(dict.fromkeys(args.horizon or HORIZONS))
    stop = 10 if args.pilot else (args.stop if args.stop is not None else 197)
    start = args.start
    if not 0 <= start < stop <= 197:
        parser.error("require 0 <= start < stop <= 197")
    lane_count = args.lanes or (1 if args.pilot else 8)
    ranges = slices(start, stop, lane_count)
    cohort = "pilot10" if args.pilot else f"cases_{start}_{stop}"

    # Validate all requested runner contracts without a model/API call.
    for arm in arms:
        for horizon in horizons:
            campaign = (
                ROOT / "data/evaluations" / args.campaign_id / "gpt4o" /
                arm / horizon / cohort / "prepare"
            )
            result = (
                ROOT / "result/OURS" / args.campaign_id / "gpt4o" /
                arm / horizon / cohort / "prepare"
            )
            command = [
                *base_command(arm, horizon, campaign, result),
                "--start", str(start), "--stop", str(stop), "--prepare-only",
            ]
            completed = subprocess.run(command, cwd=ROOT, check=False)
            if completed.returncode:
                raise SystemExit(completed.returncode)
    if args.prepare_only:
        return

    environment = os.environ.copy()
    environment["OPENAI_API_KEY"] = credential("OPENAI_API_KEY")
    processes: list[tuple[str, subprocess.Popen]] = []
    launched = []
    researcher_cursor = 0
    for arm in arms:
        for horizon in horizons:
            campaign_root = (
                ROOT / "data/evaluations" / args.campaign_id / "gpt4o" /
                arm / horizon / cohort
            )
            result_root = (
                ROOT / "result/OURS" / args.campaign_id / "gpt4o" /
                arm / horizon / cohort
            )
            campaign_root.mkdir(parents=True, exist_ok=True)
            result_root.mkdir(parents=True, exist_ok=True)
            cell_jobs = []
            for lane, (lane_start, lane_stop) in enumerate(ranges):
                researcher_url = RESEARCHER_URLS[
                    researcher_cursor % len(RESEARCHER_URLS)
                ]
                researcher_cursor += 1
                campaign = campaign_root / f"lane_{lane}"
                result = result_root / f"lane_{lane}"
                command = [
                    *base_command(arm, horizon, campaign, result),
                    "--researcher-base-url", researcher_url,
                    "--start", str(lane_start), "--stop", str(lane_stop),
                ]
                log_path = campaign_root / f"lane_{lane}.log"
                log_handle = log_path.open("ab", buffering=0)
                process = subprocess.Popen(
                    command, cwd=ROOT, env=environment,
                    stdout=log_handle, stderr=subprocess.STDOUT,
                    start_new_session=not args.wait,
                )
                log_handle.close()
                name = f"{arm}/{horizon}/lane_{lane}"
                processes.append((name, process))
                job = {
                    "name": name, "pid": process.pid,
                    "start": lane_start, "stop": lane_stop,
                    "researcher_base_url": researcher_url,
                    "log": str(log_path),
                }
                launched.append(job)
                cell_jobs.append(job)
            atomic_json(campaign_root / "launch_manifest.json", {
                "version": "final197-history-transfer-cosine-launch-v1",
                "launched_at": datetime.now(timezone.utc).isoformat(),
                "campaign_id": args.campaign_id,
                "target_model": "gpt-4o-2024-11-20",
                "researcher_model": QWEN_MODEL,
                "arm": arm, "research_horizon": horizon,
                "cohort": cohort,
                "history_transfer_mapping": str(
                    (DATA_ROOT / "history_transfer_mapping.json").resolve()
                ),
                "fresh_target_initial_analysis": True,
                "long_shared_research_stages": 7 if horizon == "long" else 0,
                "conditional_case_ab_recovery": horizon == "long",
                "branch_local_readouts": 4,
                "transport": "openai_batch_api",
                "credentials_persisted": False,
                "jobs": cell_jobs,
            })
    print(json.dumps({
        "campaign_id": args.campaign_id, "cohort": cohort,
        "arms": arms, "horizons": horizons, "jobs": launched,
    }, ensure_ascii=False), flush=True)

    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print(json.dumps({"return_codes": return_codes}, ensure_ascii=False), flush=True)
        failures = {name: code for name, code in return_codes.items() if code}
        if failures:
            raise SystemExit(max(failures.values()))


if __name__ == "__main__":
    main()

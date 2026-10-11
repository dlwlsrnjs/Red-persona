"""Launch one fixed GPT-4o pilot-10 exposure arm through Batch API."""
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
DEFAULT_CASES = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "pilot10_explicit_goal_v1/cases.json"
)
DEFAULT_CAMPAIGN = ROOT / "data/evaluations/final197_explicit_goal_pilot10_gpt4o_v1"
DEFAULT_RESULTS = ROOT / "result/OURS/final197_explicit_goal_pilot10_gpt4o_v1"
PAIRED_INPUT_ROOT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "pilot10_goal_exposure_pair_v1"
)
PAIRED_CAMPAIGN_ROOT = (
    ROOT / "data/evaluations/final197_goal_exposure_pair_pilot10_gpt4o_v18"
)
PAIRED_RESULT_ROOT = (
    ROOT / "result/OURS/final197_goal_exposure_pair_pilot10_gpt4o_v18"
)
LANES = (
    ("lane_0", 0, 3, "http://127.0.0.1:8000/v1", "OPENAI_API_KEY"),
    ("lane_1", 3, 6, "http://127.0.0.1:8001/v1", "OPENAI_API_KEY2"),
    ("lane_2", 6, 8, "http://127.0.0.1:8012/v1", "OPENAI_API_KEY"),
    ("lane_3", 8, 10, "http://127.0.0.1:8022/v1", "OPENAI_API_KEY2"),
)
PAIRED_LANES = (
    ("lane_0", 0, 3, "http://127.0.0.1:8002/v1", "OPENAI_API_KEY"),
    ("lane_1", 3, 6, "http://127.0.0.1:8003/v1", "OPENAI_API_KEY2"),
    ("lane_2", 6, 8, "http://127.0.0.1:8010/v1", "OPENAI_API_KEY"),
    ("lane_3", 8, 10, "http://127.0.0.1:8020/v1", "OPENAI_API_KEY2"),
)


def base_command(cases: Path, selection: Path) -> list[str]:
    return [
        sys.executable, "-m", "experiments.run_jmir_persona_batch_api",
        "--cases", str(cases),
        "--selection-path", str(selection),
        "--selection-key", "case_ids",
        "--target-model", "gpt-4o-2024-11-20",
        "--researcher-model", "Qwen/Qwen2.5-7B-Instruct",
        "--researcher-revision", "a09a35458c702b33eeacc393d103063234e8bc28",
        "--condition", "neutral",
        "--final-readout-protocol", "jargon_history_bridge_v1",
        "--direct-response-prompt-protocol", "counterfactual_prevention_v1",
        "--research-language-profile", "clinical_safety_terminology_v1",
        "--require-strict-harmful-goal-v3",
        "--api-mode", "batch",
        "--target-total", "10",
        "--target-workers", "128",
        "--researcher-workers", "32",
        "--max-budget-usd", "30",
        "--poll-seconds", "10",
    ]


def validate_cases(path: Path, goal_exposure: str = "explicit") -> None:
    rows = json.loads(path.read_text(encoding="utf-8"))
    ids = [str(row.get("case_id", "")) for row in rows]
    if len(ids) != 10 or len(set(ids)) != 10:
        raise ValueError("pilot input must contain exactly 10 unique cases")
    for row in rows:
        exposure = row.get("persona_goal_exposure", {})
        goal = str(row.get("original_request", "")).strip()
        persona = str(row.get("persona", ""))
        if not row.get("persona_history"):
            raise ValueError(f"persona history is missing: {row.get('case_id')}")
        if goal_exposure == "explicit":
            if (not exposure.get("target_visible") or
                    goal.casefold() not in persona.casefold()):
                raise ValueError(f"explicit goal is missing: {row.get('case_id')}")
        elif goal_exposure == "no_verbatim":
            if (exposure.get("target_visible") is True or
                    (goal and goal.casefold() in persona.casefold())):
                raise ValueError(
                    f"verbatim goal leaked into no-verbatim arm: {row.get('case_id')}"
                )
        else:
            raise ValueError(f"unsupported goal exposure arm: {goal_exposure}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--goal-exposure", choices=("explicit", "no_verbatim"),
        default="explicit",
    )
    parser.add_argument(
        "--researcher-url-set", choices=("default", "paired"), default="default",
    )
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--campaign-root", type=Path)
    parser.add_argument("--result-root", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--wait", action="store_true",
        help=("Keep the launcher attached until every lane exits. This is the "
              "reliable mode for managed terminals that reap detached children."),
    )
    parser.add_argument(
        "--only-lane", choices=[lane[0] for lane in LANES],
        help="Launch only one lane, primarily for isolated checkpoint repair.",
    )
    args = parser.parse_args()
    if args.cases is None:
        args.cases = (
            DEFAULT_CASES if args.goal_exposure == "explicit" else
            PAIRED_INPUT_ROOT / "no_verbatim_goal_cases.json"
        )
    if args.campaign_root is None:
        args.campaign_root = (
            DEFAULT_CAMPAIGN if args.goal_exposure == "explicit" else
            PAIRED_CAMPAIGN_ROOT / "no_verbatim_goal"
        )
    if args.result_root is None:
        args.result_root = (
            DEFAULT_RESULTS if args.goal_exposure == "explicit" else
            PAIRED_RESULT_ROOT / "no_verbatim_goal"
        )
    validate_cases(args.cases, args.goal_exposure)
    args.campaign_root.mkdir(parents=True, exist_ok=True)
    args.result_root.mkdir(parents=True, exist_ok=True)
    selection = args.campaign_root / "selection.json"

    prepare_command = [
        *base_command(args.cases, selection),
        "--campaign-dir", str(args.campaign_root / "prepare"),
        "--output-dir", str(args.result_root / "prepare"),
        "--prepare-only",
    ]
    completed = subprocess.run(prepare_command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    if args.prepare_only:
        return

    credentials = {
        "OPENAI_API_KEY": credential("OPENAI_API_KEY"),
        "OPENAI_API_KEY2": credential("OPENAI_API_KEY2"),
    }
    launched = []
    processes = []
    lane_table = PAIRED_LANES if args.researcher_url_set == "paired" else LANES
    active_lanes = [lane for lane in lane_table
                    if args.only_lane is None or lane[0] == args.only_lane]
    for name, start, stop, researcher_url, key_name in active_lanes:
        campaign_dir = args.campaign_root / name
        result_dir = args.result_root / name
        log_path = args.campaign_root / f"{name}.log"
        command = [
            *base_command(args.cases, selection),
            "--campaign-dir", str(campaign_dir),
            "--output-dir", str(result_dir),
            "--researcher-base-url", researcher_url,
            "--start", str(start), "--stop", str(stop),
        ]
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = credentials[key_name]
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
            "lane": name,
            "pid": process.pid,
            "start": start,
            "stop": stop,
            "case_count": stop - start,
            "researcher_base_url": researcher_url,
            "credential_name": key_name,
            "campaign_dir": str(campaign_dir),
            "result_dir": str(result_dir),
            "log": str(log_path),
        })
    manifest = {
        "protocol": "final197-goal-exposure-pilot10-gpt4o-batch-v18",
        "goal_exposure": args.goal_exposure,
        "researcher_url_set": args.researcher_url_set,
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "cases": str(args.cases.resolve()),
        "selection": str(selection),
        "target_model": "gpt-4o-2024-11-20",
        "target_transport": "openai_batch_api",
        "credentials_persisted": False,
        "lanes": launched,
    }
    atomic_json(args.campaign_root / "launch_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False))
    if args.wait:
        return_codes = {}
        for name, process in processes:
            return_codes[name] = process.wait()
        print(json.dumps({
            "status": "all_lanes_exited",
            "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failed = {name: code for name, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

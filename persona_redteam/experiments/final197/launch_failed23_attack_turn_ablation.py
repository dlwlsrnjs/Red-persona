"""Launch the failed-23 three-arm attack-turn pilot across four GPU pairs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from experiments.final197.launch_failed23_1011_pilot import (
    FAILED_CASE_IDS,
    LLAMA_MODEL,
    LLAMA_REVISION,
    LLAMA_URLS,
    QWEN_MODEL,
    QWEN_URLS,
    SLICES,
)
from experiments.final197.credentials import credential
from our_method.method_1011.adaptive_attack import (
    ADAPTIVE_MULTI_TURN_PROTOCOL,
    ATTRIBUTED_MULTI_TURN_PROTOCOL,
    SINGLE_TURN_PROTOCOL,
)
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
SOURCE_RUNTIME = Path(
    "/data1/users/ljk98/runtime_cache/persona_redteam_final197/"
    "failed23_1011_method_v1"
)
DEFAULT_RUNTIME = Path(
    "/data1/users/ljk98/runtime_cache/persona_redteam_final197/"
    "failed23_attack_turn_ablation_v7"
)
VIEWS = (
    ("single_turn", SINGLE_TURN_PROTOCOL, 4),
    ("adaptive_multiturn", ADAPTIVE_MULTI_TURN_PROTOCOL, 1),
    ("goal_attributed_multiturn", ATTRIBUTED_MULTI_TURN_PROTOCOL, 1),
)


def command(runtime: Path, lane: int, prepare_only: bool) -> list[str]:
    start, stop = SLICES[lane]
    value = [
        sys.executable,
        "-m",
        "our_method.run_attack_turn_ablation",
        "--input-dir",
        str(SOURCE_RUNTIME / "merged" / "no_verbatim"),
        "--output-root",
        str(runtime / "results" / f"lane_{lane}"),
        "--campaign-dir",
        str(runtime / "campaigns" / f"lane_{lane}"),
        "--selection-path",
        str(SOURCE_RUNTIME / "selection_failed23.json"),
        "--round-one-official-evaluation",
        str(
            SOURCE_RUNTIME / "scoring" / "no_verbatim" /
            "cares_jmir" / "results.json"
        ),
        "--round-one-success-rule",
        "cares_accept",
        "--start",
        str(start),
        "--stop",
        str(stop),
        "--condition",
        "neutral",
        "--target-model",
        QWEN_MODEL,
        "--target-base-url",
        QWEN_URLS[lane],
        "--researcher-base-url",
        LLAMA_URLS[lane],
        "--researcher-model",
        LLAMA_MODEL,
        "--researcher-revision",
        LLAMA_REVISION,
        "--abstraction-researcher",
        "openai_batch",
        "--abstraction-model",
        "gpt-4o-mini-2024-07-18",
        "--abstraction-max-budget-usd",
        "10",
        "--abstraction-max-attempts",
        "5",
        "--poll-seconds",
        "10",
        "--target-workers",
        "128",
        "--researcher-workers",
        "32",
        "--max-attack-turns",
        "4",
        "--max-target-tokens",
        "1200",
    ]
    if prepare_only:
        value.append("--prepare-only")
    return value


def validate_view_record(record: dict, protocol: str, branches: int) -> None:
    if record.get("case", {}).get("case_id") not in FAILED_CASE_IDS:
        raise ValueError("merged view contains a case outside the frozen failed-23 cohort")
    results = [result for result in record.get("results", [])
               if result.get("condition") == "neutral"]
    if len(results) != 1:
        raise ValueError("view record must contain exactly one neutral result")
    final = results[0].get("final_branches", [])
    if len(final) != branches:
        raise ValueError(f"{protocol}: expected {branches} endpoint branches")
    if protocol == SINGLE_TURN_PROTOCOL:
        if record.get("attack_turn_ablation", {}).get("protocol") != protocol:
            raise ValueError("singleton protocol metadata mismatch")
        return
    if results[0].get("attack_interaction_protocol") != protocol:
        raise ValueError("adaptive protocol metadata mismatch")
    branch = final[0]
    adaptive = branch.get("adaptive_attack", {})
    if adaptive.get("protocol") != protocol:
        raise ValueError("adaptive endpoint protocol mismatch")
    response = branch.get("attack_response", {}).get("text", "")
    messages = branch.get("attack_context", {}).get("full_messages", [])
    if not response or not messages or messages[-1] != {
        "role": "user", "content": branch.get("attack_question")
    }:
        raise ValueError("adaptive endpoint is incomplete or context-discontinuous")


def merge_views(runtime: Path) -> dict:
    summaries = {}
    for view, protocol, branches in VIEWS:
        destination = runtime / "merged" / view
        destination.mkdir(parents=True, exist_ok=True)
        records = {}
        for lane in range(len(SLICES)):
            source_dir = runtime / "results" / f"lane_{lane}" / view
            for path in sorted(source_dir.glob("*.json")):
                if path.name == "run_summary.json":
                    continue
                record = json.loads(path.read_text(encoding="utf-8"))
                validate_view_record(record, protocol, branches)
                case_id = str(record["case"]["case_id"])
                if case_id in records:
                    raise ValueError(f"duplicate {view} case {case_id}")
                records[case_id] = (path, record)
        if set(records) != set(FAILED_CASE_IDS):
            missing = sorted(set(FAILED_CASE_IDS) - set(records))
            extra = sorted(set(records) - set(FAILED_CASE_IDS))
            raise ValueError(f"{view}: missing={missing[:5]} extra={extra[:5]}")
        for case_id, (source, record) in records.items():
            target = destination / f"{case_id}.json"
            if target.exists():
                existing = json.loads(target.read_text(encoding="utf-8"))
                if existing != record:
                    raise ValueError(f"existing merged artifact differs: {target}")
            else:
                shutil.copy2(source, target)
        summary = {
            "merged_at": datetime.now(timezone.utc).isoformat(),
            "cases": len(records),
            "protocol": protocol,
            "endpoint_branches_per_case": branches,
            "source_lanes": len(SLICES),
        }
        atomic_json(destination / "run_summary.json", summary)
        summaries[view] = summary
    lane_summaries = [
        json.loads(
            (runtime / "results" / f"lane_{lane}" / "run_summary.json").read_text(
                encoding="utf-8"
            )
        )
        for lane in range(len(SLICES))
    ]
    aggregate = {
        "version": "failed23-attack-turn-ablation-merged-v7",
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(FAILED_CASE_IDS),
        "views": [view for view, _, _ in VIEWS],
        "paired_round_one_reused": True,
        "new_target_calls": {
            arm: sum(
                int(summary.get("new_target_calls", {}).get(arm, 0))
                for summary in lane_summaries
            )
            for arm in ("adaptive_multiturn", "goal_attributed_multiturn")
        },
        "new_target_cost_usd": {
            arm: sum(
                float(summary.get("new_target_cost_usd", {}).get(arm, 0.0))
                for summary in lane_summaries
            )
            for arm in ("adaptive_multiturn", "goal_attributed_multiturn", "total")
        },
        "abstraction_planner_cost_usd": sum(
            float(summary.get("abstraction_planner_cost_usd", 0.0))
            for summary in lane_summaries
        ),
        "source_lane_summaries": [
            str(runtime / "results" / f"lane_{lane}" / "run_summary.json")
            for lane in range(len(SLICES))
        ],
    }
    atomic_json(runtime / "merged" / "run_summary.json", aggregate)
    summaries["aggregate"] = aggregate
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--merge-only", action="store_true")
    args = parser.parse_args()
    if args.prepare_only and args.merge_only:
        parser.error("choose only one of --prepare-only and --merge-only")
    args.runtime.mkdir(parents=True, exist_ok=True)
    lock_handle = (args.runtime / "launch.lock").open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError(
            f"another attack-turn launcher already owns {args.runtime}"
        ) from None
    if args.merge_only:
        merged = merge_views(args.runtime)
        atomic_json(args.runtime / "completion.json", {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "merge_only": True,
            "merge": merged,
        })
        print(json.dumps(merged, ensure_ascii=False), flush=True)
        return
    temp_dir = args.runtime / "tmp"
    pycache_dir = args.runtime / "pycache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    pycache_dir.mkdir(parents=True, exist_ok=True)
    base_env = os.environ.copy()
    base_env["TMPDIR"] = str(temp_dir)
    base_env["PYTHONPYCACHEPREFIX"] = str(pycache_dir)
    api_keys = [credential("OPENAI_API_KEY"), credential("OPENAI_API_KEY2")]

    processes = []
    launched = []
    for lane in range(len(SLICES)):
        cmd = command(args.runtime, lane, args.prepare_only)
        log_path = args.runtime / "logs" / f"lane_{lane}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("ab", buffering=0)
        lane_env = base_env.copy()
        lane_env["OPENAI_API_KEY"] = api_keys[lane % len(api_keys)]
        process = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=lane_env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        handle.close()
        processes.append((lane, process))
        launched.append({
            "lane": lane,
            "pid": process.pid,
            "slice": list(SLICES[lane]),
            "target_base_url": QWEN_URLS[lane],
            "researcher_base_url": LLAMA_URLS[lane],
            "abstraction_researcher": "openai_batch",
            "abstraction_model": "gpt-4o-mini-2024-07-18",
            "credential_slot": lane % len(api_keys) + 1,
            "log": str(log_path),
        })
    atomic_json(args.runtime / "launch_manifest.json", {
        "version": "failed23-attack-turn-ablation-v7",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "prepare_only": args.prepare_only,
        "source": str(SOURCE_RUNTIME / "merged" / "no_verbatim"),
        "case_ids": list(FAILED_CASE_IDS),
        "views": [view for view, _, _ in VIEWS],
        "launched": launched,
    })
    return_codes = {str(lane): process.wait() for lane, process in processes}
    completion = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "return_codes": return_codes,
    }
    if not args.prepare_only and not any(return_codes.values()):
        completion["merge"] = merge_views(args.runtime)
    atomic_json(args.runtime / "completion.json", completion)
    print(json.dumps(completion, ensure_ascii=False), flush=True)
    if any(return_codes.values()):
        raise SystemExit(max(return_codes.values()))


if __name__ == "__main__":
    main()

"""Launch turns 2-4 when a singleton case fails either locked metric.

This is an adapter over the preserved ``engine`` copied from the existing
``our_method.run_nonaccept_max4_pilot`` implementation.  The singleton snapshot
remains unchanged and keeps enforcing zero extra turns; opting into this module
is the only way to enter recovery mode.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ADAPTER_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = ADAPTER_DIR.parents[1]
PERSONA_ROOT = PACKAGE_ROOT.parent
_IMPORT_ROOTS = (str(PERSONA_ROOT), str(PACKAGE_ROOT / "src"))
sys.path[:] = [value for value in sys.path if value not in _IMPORT_ROOTS]
sys.path[:0] = list(_IMPORT_ROOTS)

from .contracts import (  # noqa: E402
    ADAPTER_VERSION,
    DEFAULT_ROUTING_METRIC,
    ROUTING_METRICS,
    atomic_json,
    build_failure_cohort,
    validate_failure_source_run,
)
from .credentials import credential  # noqa: E402
from .integrity import require_preserved_sources  # noqa: E402


TARGET_MODEL = "gpt-4o-2024-11-20"
RESEARCHER_MODEL = "Qwen/Qwen2.5-7B-Instruct"
RESEARCHER_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
DEFAULT_RESEARCHER_URLS = (
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1",
    "http://127.0.0.1:8022/v1",
)


def balanced_slices(count: int, lanes: int) -> list[tuple[int, int]]:
    if count < 1:
        return []
    lanes = min(max(1, lanes), count)
    quotient, remainder = divmod(count, lanes)
    result = []
    start = 0
    for lane in range(lanes):
        stop = start + quotient + (1 if lane < remainder else 0)
        result.append((start, stop))
        start = stop
    return result


def engine_command(
    *,
    source_run: Path,
    selection: Path,
    round_one: Path,
    runtime: Path,
    lane: int,
    bounds: tuple[int, int],
    researcher_url: str,
    condition: str,
    target_budget: float,
    abstraction_budget: float,
    arm: str = "adaptive",
) -> list[str]:
    start, stop = bounds
    return [
        sys.executable,
        "-m",
        "singleton_1011_package.adapters.failure_only_recovery.engine",
        "--input-dir",
        str(source_run),
        "--selection-path",
        str(selection),
        "--round-one-evaluation",
        str(round_one),
        "--output-dir",
        str(runtime / "results" / f"lane_{lane}"),
        "--campaign-dir",
        str(runtime / "campaigns" / f"lane_{lane}"),
        "--start",
        str(start),
        "--stop",
        str(stop),
        "--condition",
        condition,
        "--arm",
        arm,
        "--target-model",
        TARGET_MODEL,
        "--researcher-model",
        RESEARCHER_MODEL,
        "--researcher-base-url",
        researcher_url,
        "--researcher-revision",
        RESEARCHER_REVISION,
        "--target-workers",
        "128",
        "--researcher-workers",
        "32",
        "--max-target-tokens",
        "1200",
        "--target-max-budget-usd",
        str(target_budget),
        "--abstraction-model",
        TARGET_MODEL,
        "--abstraction-max-budget-usd",
        str(abstraction_budget),
        "--abstraction-max-attempts",
        "5",
        "--poll-seconds",
        "10",
    ]


def validate_engine() -> None:
    require_preserved_sources()
    required = (
        ADAPTER_DIR / "adaptive_core.py",
        ADAPTER_DIR / "attack_turn_core.py",
        ADAPTER_DIR / "engine.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "failure-only adapter is missing an engine dependency: "
            + ", ".join(missing)
        )


def merge_lanes(
    runtime: Path,
    case_ids: list[str],
    lane_count: int,
    *,
    arm: str,
) -> dict[str, Any]:
    destination = runtime / "merged" / "trajectories"
    destination.mkdir(parents=True, exist_ok=True)
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    for lane in range(lane_count):
        lane_dir = runtime / "results" / f"lane_{lane}"
        summary_path = lane_dir / "run_summary.json"
        if not summary_path.is_file():
            raise FileNotFoundError(summary_path)
        for path in sorted(lane_dir.glob("*.json")):
            if path.name == "run_summary.json":
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            case_id = str(value.get("case", {}).get("case_id", ""))
            if value.get("target_model") != TARGET_MODEL:
                raise ValueError(f"{case_id}: recovery target is not GPT-4o")
            if value.get("strategy_arm") != arm:
                raise ValueError(f"{case_id}: recovery strategy arm mismatch")
            adaptive = value.get("adaptive_max4", {})
            if adaptive.get("executed_turns") != 4:
                raise ValueError(f"{case_id}: recovery did not reach turn four")
            if adaptive.get("round_one_success") is not False:
                raise ValueError(f"{case_id}: a round-one success entered recovery")
            if case_id in found:
                raise ValueError(f"duplicate recovered case: {case_id}")
            found[case_id] = (path, value)
    if set(found) != set(case_ids):
        raise ValueError(
            f"recovery coverage mismatch missing={sorted(set(case_ids)-set(found))} "
            f"extra={sorted(set(found)-set(case_ids))}"
        )
    for case_id, (source, value) in found.items():
        target = destination / f"{case_id}.json"
        if target.exists() and json.loads(target.read_text(encoding="utf-8")) != value:
            raise ValueError(f"existing merged trajectory differs: {target}")
        if not target.exists():
            shutil.copy2(source, target)
    summary = {
        "version": ADAPTER_VERSION,
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(found),
        "target_model": TARGET_MODEL,
        "turns": 4,
        "candidates_per_turn": 4,
        "reused_round_one_responses": 4 * len(found),
        "new_target_responses": 12 * len(found),
        "official_metric_used_for_path_selection": False,
        "forced_to_turn_four": True,
        "strategy_arm": arm,
    }
    atomic_json(runtime / "merged" / "run_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--singleton-scoring", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--expected-singleton-cases", type=int)
    parser.add_argument("--condition", default="neutral")
    parser.add_argument(
        "--routing-metric",
        choices=ROUTING_METRICS,
        default=DEFAULT_ROUTING_METRIC,
        help=(
            "failure gate; default 'harmbench' retries a case when all four "
            "singleton responses are HarmBench-negative"
        ),
    )
    parser.add_argument(
        "--arm", choices=("adaptive", "goal_attributed"), default="adaptive"
    )
    parser.add_argument("--researcher-url", action="append", dest="researcher_urls")
    parser.add_argument("--lanes", type=int, default=4)
    parser.add_argument("--only-lane", type=int)
    parser.add_argument("--target-budget-per-lane", type=float, default=40.0)
    parser.add_argument("--abstraction-budget-per-lane", type=float, default=10.0)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--merge-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--allow-one-key", action="store_true")
    args = parser.parse_args()
    validate_engine()
    args.runtime.mkdir(parents=True, exist_ok=True)
    adapter_input = args.runtime / "adapter_input"
    selection = build_failure_cohort(
        args.singleton_scoring,
        adapter_input,
        target_model=TARGET_MODEL,
        expected_cases=args.expected_singleton_cases,
        routing_metric=args.routing_metric,
    )
    case_ids = list(map(str, selection["failure_case_ids"]))
    round_one_path = adapter_input / "round_one_failures.json"
    selection["source_validation"] = validate_failure_source_run(
        args.source_run,
        round_one_path,
        case_ids,
        condition=args.condition,
    )
    atomic_json(adapter_input / "selection.json", selection)
    if not case_ids:
        atomic_json(args.runtime / "completion.json", {
            "version": ADAPTER_VERSION,
            "status": "complete_no_failures",
            "selection": selection,
        })
        print(json.dumps(selection, ensure_ascii=False, indent=2))
        return
    slices = balanced_slices(len(case_ids), args.lanes)
    if args.only_lane is not None and not 0 <= args.only_lane < len(slices):
        parser.error(f"--only-lane must be in [0, {len(slices) - 1}]")
    if args.prepare_only:
        print(json.dumps(selection, ensure_ascii=False, indent=2))
        return
    if args.merge_only:
        print(json.dumps(
            merge_lanes(args.runtime, case_ids, len(slices), arm=args.arm),
            ensure_ascii=False,
            indent=2,
        ))
        return

    urls = tuple(args.researcher_urls or DEFAULT_RESEARCHER_URLS)
    key_names = ["OPENAI_API_KEY", "OPENAI_API_KEY2"]
    keys = []
    for name in key_names:
        try:
            keys.append(credential(name))
        except RuntimeError:
            if name == "OPENAI_API_KEY2" and args.allow_one_key:
                continue
            raise
    launched = []
    processes = []
    for lane, bounds in enumerate(slices):
        if args.only_lane is not None and lane != args.only_lane:
            continue
        lane_output = args.runtime / "results" / f"lane_{lane}"
        if (lane_output / "run_summary.json").is_file():
            launched.append({"lane": lane, "status": "already_complete"})
            continue
        command = engine_command(
            source_run=args.source_run.resolve(),
            selection=(adapter_input / "selection.json").resolve(),
            round_one=round_one_path.resolve(),
            runtime=args.runtime.resolve(),
            lane=lane,
            bounds=bounds,
            researcher_url=urls[lane % len(urls)],
            condition=args.condition,
            target_budget=args.target_budget_per_lane,
            abstraction_budget=args.abstraction_budget_per_lane,
            arm=args.arm,
        )
        environment = os.environ.copy()
        environment["OPENAI_API_KEY"] = keys[lane % len(keys)]
        prior = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            value for value in (str(PERSONA_ROOT), str(PACKAGE_ROOT / "src"), prior)
            if value
        )
        log = args.runtime / "logs" / f"lane_{lane}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        handle = log.open("ab", buffering=0)
        process = subprocess.Popen(
            command,
            cwd=PERSONA_ROOT,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        handle.close()
        processes.append((lane, process))
        launched.append({
            "lane": lane,
            "pid": process.pid,
            "slice": list(bounds),
            "researcher_url": urls[lane % len(urls)],
            "credential_slot": lane % len(keys) + 1,
            "log": str(log),
            "status": "launched",
        })
    manifest = {
        "version": ADAPTER_VERSION,
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(args.source_run.resolve()),
        "singleton_scoring": str(args.singleton_scoring.resolve()),
        "routing_metric": args.routing_metric,
        "selection": selection,
        "target_model": TARGET_MODEL,
        "researcher_model": RESEARCHER_MODEL,
        "new_turns": [2, 3, 4],
        "strategy_arm": args.arm,
        "candidates_per_turn": 4,
        "lanes": launched,
        "credentials_persisted": False,
    }
    atomic_json(args.runtime / "launch_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    if not args.wait:
        return
    failures = []
    for lane, process in processes:
        code = process.wait()
        if code:
            failures.append({"lane": lane, "return_code": code})
    if failures:
        atomic_json(args.runtime / "generation_failures.json", failures)
        raise RuntimeError(f"recovery lanes failed: {failures}")
    summary = merge_lanes(
        args.runtime, case_ids, len(slices), arm=args.arm
    )
    atomic_json(args.runtime / "completion.json", {
        "version": ADAPTER_VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

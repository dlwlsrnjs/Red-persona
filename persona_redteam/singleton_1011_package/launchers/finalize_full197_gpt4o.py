"""Wait for all Final-197 GPT-4o arms, merge them, and launch Batch judges.

This supervisor never submits generation requests.  It only observes the lane
manifests/results produced by ``launch_full197_gpt4o.py`` and therefore can be
restarted safely while a campaign is running.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from _bootstrap import DEFAULT_WORKSPACE_ROOT, PACKAGE_ROOT, subprocess_env


DEFAULT_MATRIX_ID = "final197_1011_singleton_gpt4o_v1"
DEFAULT_ARMS = ("no_verbatim", "explicit", "no_history")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_manifest(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"missing generation manifest: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    lanes = value.get("lanes")
    if not isinstance(lanes, list) or len(lanes) != 8:
        raise ValueError(f"{path} must register exactly eight lanes")
    return value


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lane_status(manifest: dict, result_root: Path) -> tuple[int, list[str]]:
    complete = 0
    stopped = []
    for lane in manifest["lanes"]:
        name = lane["lane"]
        if (result_root / name / "run_summary.json").is_file():
            complete += 1
        elif not pid_alive(int(lane["pid"])):
            stopped.append(name)
    return complete, stopped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--matrix-id", default=DEFAULT_MATRIX_ID)
    parser.add_argument("--arm", action="append", dest="arms")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-hours", type=float, default=24.0)
    parser.add_argument("--skip-evaluation", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace_root.resolve()
    arms = tuple(args.arms or DEFAULT_ARMS)
    campaign_base = workspace / "data/evaluations" / args.matrix_id / "gpt4o"
    result_base = workspace / "result/OURS" / args.matrix_id / "gpt4o"
    manifests = {
        arm: read_manifest(campaign_base / arm / "launch_manifest.json")
        for arm in arms
    }

    deadline = time.monotonic() + max(0.1, args.timeout_hours) * 3600
    previous = None
    while True:
        status = {}
        failed = {}
        for arm in arms:
            complete, stopped = lane_status(manifests[arm], result_base / arm)
            status[arm] = complete
            if stopped:
                failed[arm] = stopped
        if status != previous:
            print(json.dumps({"generation_lanes_complete": status}, ensure_ascii=False), flush=True)
            previous = status
        if failed:
            raise RuntimeError(f"generation lanes stopped before completion: {failed}")
        if all(count == 8 for count in status.values()):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"generation did not finish within {args.timeout_hours} hours")
        time.sleep(max(5, args.poll_seconds))

    merge_records = {}
    for arm in arms:
        result_root = result_base / arm
        command = [
            sys.executable, str(PACKAGE_ROOT / "launchers/merge_lanes.py"),
            "--result-root", str(result_root), "--output-dir", str(result_root / "merged"),
            "--expected-cases", "197", "--lane-count", "8",
        ]
        completed = subprocess.run(
            command, cwd=PACKAGE_ROOT, env=subprocess_env(), check=True,
            capture_output=True, text=True,
        )
        merge_records[arm] = json.loads(completed.stdout)
        print(json.dumps({"merged": arm, **merge_records[arm]}, ensure_ascii=False), flush=True)

    record = {
        "version": "final197-gpt4o-auto-finalizer-v1",
        "completed_generation_at": datetime.now(timezone.utc).isoformat(),
        "matrix_id": args.matrix_id,
        "arms": list(arms),
        "merge": merge_records,
        "evaluation_jobs": [],
    }
    record_path = campaign_base / "auto_finalizer.json"
    atomic_json(record_path, record)
    if args.skip_evaluation:
        return

    processes = []
    for arm in arms:
        campaign_root = campaign_base / arm
        output_dir = campaign_root / "scoring"
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable, str(PACKAGE_ROOT / "launchers/evaluate_gpt4o.py"),
            "--run-dir", str(result_base / arm / "merged"),
            "--selection", str(campaign_root / "selection.json"),
            "--output-dir", str(output_dir),
            "--expected-cases", "197", "--execute", "--wait",
        ]
        log_path = output_dir / "auto_evaluate_gpt4o.log"
        log_handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command, cwd=PACKAGE_ROOT, env=subprocess_env(),
            stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True,
        )
        log_handle.close()
        processes.append((arm, process, log_path))
        record["evaluation_jobs"].append({
            "arm": arm, "pid": process.pid, "log": str(log_path),
        })
    atomic_json(record_path, record)
    print(json.dumps({"evaluation_jobs": record["evaluation_jobs"]}, ensure_ascii=False), flush=True)

    codes = {arm: process.wait() for arm, process, _ in processes}
    record["evaluation_return_codes"] = codes
    record["completed_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(record_path, record)
    print(json.dumps({"evaluation_return_codes": codes}, ensure_ascii=False), flush=True)
    if any(codes.values()):
        raise SystemExit(max(codes.values()))


if __name__ == "__main__":
    main()

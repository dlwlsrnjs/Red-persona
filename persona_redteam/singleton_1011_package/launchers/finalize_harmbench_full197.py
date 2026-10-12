"""Run HarmBench for all Final-197 arms after GPT-4o judging completes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from _bootstrap import DEFAULT_WORKSPACE_ROOT, PACKAGE_ROOT


DEFAULT_MATRIX_ID = "final197_1011_singleton_gpt4o_v1"
DEFAULT_ARMS = ("no_verbatim", "explicit", "no_history")
DEFAULT_GPUS = (0, 3, 4)
TORCH_PYTHON = Path(os.environ.get("HARMBENCH_PYTHON", sys.executable))


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def cmdline(pid: int) -> str:
    path = Path(f"/proc/{pid}/cmdline")
    if not path.is_file():
        return ""
    return path.read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace")


def stop_extra_qwen_supervisor(pid: int, timeout_seconds: int = 180) -> None:
    command = cmdline(pid)
    required = (
        "launch_qwen_replicas.py",
        "final197_1011_singleton_gpt4o_v1/qwen_extra_replicas",
    )
    if not all(value in command for value in required):
        raise RuntimeError(
            f"refusing to stop PID {pid}; it is not the registered extra-Qwen supervisor"
        )
    os.kill(pid, signal.SIGINT)
    deadline = time.monotonic() + timeout_seconds
    while cmdline(pid):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"extra-Qwen supervisor PID {pid} did not stop")
        time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--matrix-id", default=DEFAULT_MATRIX_ID)
    parser.add_argument("--arm", action="append", dest="arms")
    parser.add_argument("--gpu", action="append", dest="gpus", type=int)
    parser.add_argument("--qwen-supervisor-pid", type=int, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-hours", type=float, default=30.0)
    parser.add_argument("--torch-python", type=Path, default=TORCH_PYTHON)
    args = parser.parse_args()

    workspace = args.workspace_root.resolve()
    arms = tuple(args.arms or DEFAULT_ARMS)
    gpus = tuple(args.gpus or DEFAULT_GPUS)
    if len(gpus) < len(arms):
        parser.error("provide at least one distinct GPU per arm")
    if len(set(gpus[:len(arms)])) != len(arms):
        parser.error("HarmBench arm GPUs must be distinct")
    if not args.torch_python.is_file():
        raise FileNotFoundError(f"PyTorch Python not found: {args.torch_python}")

    campaign_base = workspace / "data/evaluations" / args.matrix_id / "gpt4o"
    result_base = workspace / "result/OURS" / args.matrix_id / "gpt4o"
    deadline = time.monotonic() + max(0.1, args.timeout_hours) * 3600
    previous = None
    while True:
        ready = {
            arm: (
                (result_base / arm / "merged" / "run_summary.json").is_file()
                and (campaign_base / arm / "scoring/recovery_behavior.json").is_file()
                and (campaign_base / arm / "scoring/cares_jmir/results.json").is_file()
            )
            for arm in arms
        }
        if ready != previous:
            print(json.dumps({"gpt4o_evaluation_ready": ready}, ensure_ascii=False), flush=True)
            previous = ready
        if all(ready.values()):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"GPT-4o evaluation did not finish within {args.timeout_hours} hours")
        time.sleep(max(5, args.poll_seconds))

    stop_extra_qwen_supervisor(args.qwen_supervisor_pid)
    print(json.dumps({"stopped_extra_qwen_supervisor": args.qwen_supervisor_pid}), flush=True)
    # Give CUDA contexts a short grace period after the four vLLM children exit.
    time.sleep(10)

    processes = []
    jobs = []
    for arm, gpu in zip(arms, gpus):
        scoring = campaign_base / arm / "scoring"
        command = [
            str(args.torch_python), str(PACKAGE_ROOT / "launchers/evaluate_harmbench.py"),
            "--run-dir", str(result_base / arm / "merged"),
            "--recovery-evaluation", str(scoring / "recovery_behavior.json"),
            "--output", str(scoring / "harmbench.json"),
            "--expected-cases", "197", "--device", "cuda:0",
        ]
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(gpu)
        log_path = scoring / "auto_harmbench.log"
        log_handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command, cwd=PACKAGE_ROOT, env=env,
            stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True,
        )
        log_handle.close()
        processes.append((arm, process))
        jobs.append({"arm": arm, "gpu": gpu, "pid": process.pid, "log": str(log_path)})

    record_path = campaign_base / "auto_harmbench_finalizer.json"
    record = {
        "version": "final197-harmbench-auto-finalizer-v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "matrix_id": args.matrix_id,
        "jobs": jobs,
    }
    atomic_json(record_path, record)
    print(json.dumps({"harmbench_jobs": jobs}, ensure_ascii=False), flush=True)
    codes = {arm: process.wait() for arm, process in processes}
    record["return_codes"] = codes
    record["completed_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(record_path, record)
    print(json.dumps({"harmbench_return_codes": codes}, ensure_ascii=False), flush=True)
    if any(codes.values()):
        raise SystemExit(max(codes.values()))


if __name__ == "__main__":
    main()

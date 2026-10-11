"""Keep four additional single-GPU Qwen researcher replicas alive."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path("/data1/users/ljk98/envs/VLLM-VL-LABEL/bin/python")
VLLM = Path("/data1/users/ljk98/envs/VLLM-VL-LABEL/bin/vllm")
MODEL = Path(
    "/data1/users/ljk98/hf_cache/hub/"
    "models--Qwen--Qwen2.5-7B-Instruct/snapshots/"
    "a09a35458c702b33eeacc393d103063234e8bc28"
)
REPLICAS = ((0, 8002), (3, 8003), (4, 8010), (7, 8020))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-dir", type=Path,
        default=ROOT / "data/evaluations/qwen_replicas_final197",
    )
    args = parser.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=True)

    children: list[tuple[subprocess.Popen, object]] = []
    try:
        for gpu, port in REPLICAS:
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = str(gpu)
            env["PATH"] = str(PYTHON.parent) + os.pathsep + env.get("PATH", "")
            log_handle = (args.log_dir / f"gpu_{gpu}_port_{port}.log").open(
                "ab", buffering=0
            )
            command = [
                str(PYTHON), str(VLLM), "serve", str(MODEL),
                "--served-model-name", "Qwen/Qwen2.5-7B-Instruct",
                "--host", "127.0.0.1", "--port", str(port),
                "--dtype", "bfloat16", "--max-model-len", "32768",
                "--gpu-memory-utilization", "0.80",
                "--enable-prefix-caching", "--enforce-eager",
            ]
            process = subprocess.Popen(
                command, cwd=ROOT, env=env,
                stdout=log_handle, stderr=subprocess.STDOUT,
            )
            children.append((process, log_handle))
            print(f"started gpu={gpu} port={port} pid={process.pid}", flush=True)

        while True:
            failed = [process.returncode for process, _ in children
                      if process.poll() is not None]
            if failed:
                raise RuntimeError(f"Qwen replica exited: {failed}")
            time.sleep(2)
    except (KeyboardInterrupt, RuntimeError) as exc:
        print(str(exc), file=sys.stderr, flush=True)
        for process, _ in children:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
        for process, _ in children:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
        if isinstance(exc, RuntimeError):
            raise SystemExit(1) from exc
    finally:
        for _, log_handle in children:
            log_handle.close()


if __name__ == "__main__":
    main()

"""Run the four Qwen replicas registered by the Final-197 matrix."""
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
REPLICAS = ((1, 8000), (5, 8001), (2, 8012), (6, 8022))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-dir", type=Path,
        default=ROOT / "data/evaluations/final197_qwen_matrix_replicas",
    )
    args = parser.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=True)
    children: list[tuple[subprocess.Popen, object]] = []
    try:
        for gpu, port in REPLICAS:
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = str(gpu)
            env["PATH"] = str(PYTHON.parent) + os.pathsep + env.get("PATH", "")
            log_handle = (args.log_dir / f"gpu_{gpu}_qwen_{port}.log").open(
                "ab", buffering=0
            )
            process = subprocess.Popen([
                str(PYTHON), str(VLLM), "serve", str(MODEL),
                "--served-model-name", "Qwen/Qwen2.5-7B-Instruct",
                "--host", "127.0.0.1", "--port", str(port),
                # The accumulated research history plus a final recovery branch
                # can exceed 16K even after planner-side transcript compaction.
                # Qwen2.5 supports the larger window and a 7B replica fits it on
                # one 80GB H100, so keep enough headroom for the attack response.
                "--dtype", "bfloat16", "--max-model-len", "32768",
                "--gpu-memory-utilization", "0.80", "--max-num-seqs", "128",
                "--enable-prefix-caching", "--enforce-eager",
            ], cwd=ROOT, env=env, stdout=log_handle, stderr=subprocess.STDOUT)
            children.append((process, log_handle))
            print(f"started gpu={gpu} model=qwen port={port} pid={process.pid}", flush=True)
        while True:
            failed = [process.returncode for process, _ in children
                      if process.poll() is not None]
            if failed:
                raise RuntimeError(f"Final-197 Qwen replica exited: {failed}")
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

"""Run four Llama researcher replicas on the currently free H100s."""
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
LLAMA = Path(
    "/data1/users/ljk98/models/Llama-3.1-8B-Instruct/"
    "0e9e39f249a16976918f6564b8830bc894c89659"
)
REPLICAS = ((0, 8100), (3, 8101), (4, 8102), (7, 8103))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-dir", type=Path,
        default=ROOT / "data/evaluations/final197_cross_target_replicas",
    )
    args = parser.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=True)
    children: list[tuple[subprocess.Popen, object]] = []
    try:
        for gpu, port in REPLICAS:
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = str(gpu)
            env["PATH"] = str(PYTHON.parent) + os.pathsep + env.get("PATH", "")
            log_handle = (args.log_dir / f"gpu_{gpu}_llama_{port}.log").open(
                "ab", buffering=0
            )
            command = [
                str(PYTHON), str(VLLM), "serve", str(LLAMA),
                "--served-model-name", "meta-llama/Llama-3.1-8B-Instruct",
                "--host", "127.0.0.1", "--port", str(port),
                "--dtype", "bfloat16", "--max-model-len", "16384",
                "--gpu-memory-utilization", "0.80",
                "--max-num-seqs", "128", "--enable-prefix-caching",
                "--enforce-eager",
            ]
            process = subprocess.Popen(
                command, cwd=ROOT, env=env,
                stdout=log_handle, stderr=subprocess.STDOUT,
            )
            children.append((process, log_handle))
            print(
                f"started gpu={gpu} model=llama port={port} pid={process.pid}",
                flush=True,
            )
        while True:
            failed = [process.returncode for process, _ in children
                      if process.poll() is not None]
            if failed:
                raise RuntimeError(f"cross-target replica exited: {failed}")
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

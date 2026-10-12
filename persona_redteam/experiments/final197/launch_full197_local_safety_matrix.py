"""Run HarmBench, Qwen3Guard, and Nemotron across all six completed cells."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GPU_PYTHON = Path("/data1/users/ljk98/envs/VLLM-VL-LABEL/bin/python")


def gpu_python() -> Path:
    """Return the interpreter that owns the CUDA/Transformers dependencies."""
    path = Path(os.environ.get("FINAL197_GPU_PYTHON", DEFAULT_GPU_PYTHON))
    if not path.is_file():
        raise FileNotFoundError(
            f"GPU Python was not found at {path}. Set FINAL197_GPU_PYTHON."
        )
    return path


def main() -> None:
    python = gpu_python()
    jobs = (
        ("harmbench_a", "harmbench", "cuda:0", 0, 3),
        ("harmbench_b", "harmbench", "cuda:7", 3, 6),
        ("qwen3guard_a", "qwen3guard", "cuda:1", 0, 2),
        ("qwen3guard_b", "qwen3guard", "cuda:2", 2, 4),
        ("qwen3guard_c", "qwen3guard", "cuda:3", 4, 6),
        ("nemotron_a", "nemotron", "cuda:4", 0, 2),
        ("nemotron_b", "nemotron", "cuda:5", 2, 4),
        ("nemotron_c", "nemotron", "cuda:6", 4, 6),
    )
    processes = []
    for name, evaluator, device, start, stop in jobs:
        process = subprocess.Popen([
            str(python), "-m",
            "experiments.final197.run_local_safety_evaluator_worker",
            "--evaluator", evaluator, "--device", device,
            "--start", str(start), "--stop", str(stop),
        ], cwd=ROOT)
        processes.append((name, process))
    return_codes = {name: process.wait() for name, process in processes}
    print(json.dumps({
        "status": "local_safety_matrix_exited", "return_codes": return_codes,
    }, ensure_ascii=False), flush=True)
    failed = {name: code for name, code in return_codes.items() if code}
    if failed:
        raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

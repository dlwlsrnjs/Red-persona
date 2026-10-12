"""Run one local safety evaluator over a slice of completed matrix cells."""
from __future__ import annotations

import argparse
from pathlib import Path

from experiments.evaluate_harmbench_direct_response import run_directory as run_harmbench
from experiments.evaluate_nemotron3_content_safety import run_directory as run_nemotron
from experiments.evaluate_qwen3guard_direct_response import run_directory as run_qwen_guard
from experiments.final197.launch_full197_arm import ARMS, MATRIX_ID, TARGETS


ROOT = Path(__file__).resolve().parents[2]
CELLS = tuple((target, arm) for target in TARGETS for arm in ARMS)
MODELS = {
    "harmbench": (
        "/data1/users/ljk98/hf_cache/hub/models--cais--HarmBench-Llama-2-13b-cls/"
        "snapshots/bda705349d1144fa618770bea64d99ce54e3835b"
    ),
    "qwen3guard": (
        "/data1/users/ljk98/hf_cache/hub/models--Qwen--Qwen3Guard-Gen-8B/"
        "snapshots/4505cb1a6f1864f21f8b27f7daf1b9a1aab6edbb"
    ),
    "nemotron": (
        "/data1/users/ljk98/hf_cache/models--nvidia--Nemotron-3-Content-Safety/"
        "snapshots/b47f6f6c18dc7d11a786abbbca2510cba58ede20"
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluator", choices=tuple(MODELS), required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int, default=len(CELLS))
    args = parser.parse_args()
    for target, arm in CELLS[args.start:args.stop]:
        run_dir = ROOT / "result/OURS" / MATRIX_ID / target / arm / "merged"
        score = ROOT / "data/evaluations" / MATRIX_ID / target / arm / "scoring"
        recovery = score / "recovery_behavior.json"
        if args.evaluator == "harmbench":
            run_harmbench(
                run_dir, recovery, score / "harmbench.json",
                model_name=MODELS[args.evaluator], batch_size=32,
                device=args.device, expected_cases=197,
            )
        elif args.evaluator == "qwen3guard":
            run_qwen_guard(
                run_dir, recovery, score / "qwen3guard.json",
                model_name=MODELS[args.evaluator], batch_size=16,
                device=args.device, expected_cases=197,
            )
        else:
            run_nemotron(
                run_dir, recovery, score / "nemotron3_content_safety.json",
                model_name=MODELS[args.evaluator], batch_size=16,
                device=args.device, expected_cases=197,
            )


if __name__ == "__main__":
    main()

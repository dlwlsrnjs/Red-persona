"""Launch all two-target by three-context Final-197 experiment cells."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

from experiments.final197.launch_full197_arm import (
    ARMS, LLAMA_URLS, QWEN_URLS, TARGETS,
)


ROOT = Path(__file__).resolve().parents[2]


def preflight(urls: tuple[str, ...]) -> list[str]:
    failures = []
    for base_url in urls:
        try:
            with urlopen(base_url.rstrip("/") + "/models", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not payload.get("data"):
                failures.append(f"{base_url}: empty model list")
        except Exception as exc:
            failures.append(f"{base_url}: {type(exc).__name__}: {exc}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    subprocess.run([
        sys.executable, "-m",
        "experiments.final197.prepare_abstract_goal_persona_arm",
    ], cwd=ROOT, check=True)
    subprocess.run([
        sys.executable, "-m",
        "experiments.final197.prepare_full197_experiment_matrix",
    ], cwd=ROOT, check=True)
    if args.prepare_only:
        return
    failures = preflight((*QWEN_URLS, *LLAMA_URLS))
    if failures:
        raise SystemExit(
            "local model preflight failed; no experiment was launched:\n"
            + "\n".join(failures)
        )
    processes = []
    for target in TARGETS:
        for arm in ARMS:
            process = subprocess.Popen([
                sys.executable, "-m", "experiments.final197.launch_full197_arm",
                "--target", target, "--arm", arm, "--wait",
            ], cwd=ROOT)
            processes.append((f"{target}/{arm}", process))
    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print(json.dumps({
            "status": "matrix_exited", "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failed = {name: code for name, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

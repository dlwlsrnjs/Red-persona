"""Launch the paired explicit/no-verbatim GPT-4o pilot after Qwen preflight."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import URLError
from urllib.request import urlopen

from experiments.final197.launch_pilot10_batch import PAIRED_LANES


ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "pilot10_goal_exposure_pair_v1"
)
CAMPAIGN_ROOT = (
    ROOT / "data/evaluations/final197_goal_exposure_pair_pilot10_gpt4o_v18"
)
RESULT_ROOT = (
    ROOT / "result/OURS/final197_goal_exposure_pair_pilot10_gpt4o_v18"
)
ARMS = {
    "no_verbatim": "no_verbatim_goal_cases.json",
    "explicit": "explicit_goal_cases.json",
}


def researcher_preflight(timeout: float = 2.0) -> list[str]:
    failures = []
    for lane, _start, _stop, base_url, _key in PAIRED_LANES:
        url = base_url.removesuffix("/v1") + "/v1/models"
        try:
            with urlopen(url, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not payload.get("data"):
                failures.append(f"{lane}: empty model list at {url}")
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{lane}: {url}: {exc}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    subprocess.run([
        sys.executable, "-m",
        "experiments.final197.prepare_pilot10_goal_exposure_pair",
    ], cwd=ROOT, check=True)
    if args.prepare_only:
        return
    failures = researcher_preflight()
    if failures:
        raise SystemExit(
            "Qwen researcher preflight failed; no Batch target requests were submitted:\n" +
            "\n".join(failures)
        )

    processes = []
    for arm, filename in ARMS.items():
        command = [
            sys.executable, "-m", "experiments.final197.launch_pilot10_batch",
            "--goal-exposure", arm,
            "--researcher-url-set", "paired",
            "--cases", str(INPUT_ROOT / filename),
            "--campaign-root", str(CAMPAIGN_ROOT / arm),
            "--result-root", str(RESULT_ROOT / arm),
            "--wait",
        ]
        process = subprocess.Popen(command, cwd=ROOT)
        processes.append((arm, process))
    if args.wait:
        return_codes = {arm: process.wait() for arm, process in processes}
        print(json.dumps({
            "status": "paired_generation_exited",
            "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failed = {arm: code for arm, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

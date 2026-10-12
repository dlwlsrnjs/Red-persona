"""Rerun the fixed 23-case Qwen failure cohort with 1011 Method v1.

The outcome-selected cohort is inherited unchanged from the earlier final-branch
repair audit.  We run matched with-history and no-history inputs so the new
conditional Case-A/Case-B recovery can be compared with the prior results.
Four already-running Qwen target replicas and four Llama researcher replicas
are shared across the eight lanes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.prepare_full197_experiment_matrix import ARM_PATHS
from pipeline.official_selection import METHOD as OFFICIAL_SELECTION_METHOD
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME = Path(
    "/data1/users/ljk98/runtime_cache/persona_redteam_final197/"
    "failed23_1011_method_v1"
)
VERSION = "failed23-1011-method-v1"
ARMS = ("no_verbatim", "no_history")
QWEN_MODEL = "Qwen/Qwen2.5-7B-Instruct"
LLAMA_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
LLAMA_REVISION = "0e9e39f249a16976918f6564b8830bc894c89659"
SLICES = ((0, 6), (6, 12), (12, 18), (18, 23))
QWEN_URLS = (
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1",
    "http://127.0.0.1:8022/v1",
)
LLAMA_URLS = (
    "http://127.0.0.1:8100/v1",
    "http://127.0.0.1:8101/v1",
    "http://127.0.0.1:8102/v1",
    "http://127.0.0.1:8103/v1",
)
FAILED_CASE_IDS = (
    "ailuminate-ssh-airr_practice_1_0_150302",
    "ailuminate-ssh-airr_practice_1_0_90844",
    "jmir-source-1350",
    "jmir-source-1363",
    "jmir-source-1376",
    "jmir-source-1383",
    "jmir-source-1400",
    "jmir-source-1421",
    "jmir-source-1428",
    "jmir-source-1445",
    "jmir-source-1468",
    "jmir-source-1469",
    "jmir-source-1474",
    "jmir-source-1496",
    "jmir-source-1499",
    "jmir-source-1575",
    "jmir-source-1621",
    "jmir-source-1623",
    "mvrcii-text-00002",
    "mvrcii-text-01194",
    "mvrcii-text-02240",
    "mvrcii-text-03379",
    "mvrcii-text-03497",
)


def runner_command(
    runtime: Path,
    selection: Path,
    arm: str,
    lane: int,
    *,
    prepare_only: bool,
) -> list[str]:
    start, stop = SLICES[lane]
    # The production runner validates the canonical active case before applying
    # a registered ablation.  Build no-history from the audited no-verbatim
    # source at runtime; this is byte-equivalent to the frozen exported arm.
    cases = ARM_PATHS["no_verbatim"] if arm == "no_history" else ARM_PATHS[arm]
    command = [
        sys.executable,
        "-m",
        "our_method.run_1011_method",
        "--cases",
        str(cases),
        "--selection-path",
        str(selection),
        "--selection-key",
        "final_case_ids",
        "--condition",
        "neutral",
        "--target-total",
        str(len(FAILED_CASE_IDS)),
        "--start",
        str(start),
        "--stop",
        str(stop),
        "--campaign-dir",
        str(runtime / "campaigns" / arm / f"lane_{lane}"),
        "--output-dir",
        str(runtime / "results" / arm / f"lane_{lane}"),
        "--target-model",
        QWEN_MODEL,
        "--researcher-model",
        LLAMA_MODEL,
        "--researcher-revision",
        LLAMA_REVISION,
        "--target-base-url",
        QWEN_URLS[lane],
        "--researcher-base-url",
        LLAMA_URLS[lane],
        "--target-workers",
        "128",
        "--researcher-workers",
        "32",
        "--final-readout-protocol",
        "safety_negative_examples_v1",
        "--direct-response-prompt-protocol",
        "counterfactual_prevention_v1",
        "--research-language-profile",
        "clinical_safety_terminology_v1",
        "--require-strict-harmful-goal-v3",
    ]
    if arm == "no_history":
        command.extend(("--ablation-variant", "no_prior_dialogue"))
    if prepare_only:
        command.append("--prepare-only")
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    args.runtime.mkdir(parents=True, exist_ok=True)
    selection = args.runtime / "selection_failed23.json"
    if not selection.exists():
        atomic_json(
            selection,
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "target_total": len(FAILED_CASE_IDS),
                "selection_method": OFFICIAL_SELECTION_METHOD,
                "final_case_ids": list(FAILED_CASE_IDS),
                "cohort_source": (
                    "qwen-no-history-final-branch-repair-v2 "
                    "unresolved_branch_ids"
                ),
                "outcome_selected_pilot": True,
                "method_protocol": "1011_method_v1",
            },
        )

    temp_dir = args.runtime / "tmp"
    pycache_dir = args.runtime / "pycache"
    temp_dir.mkdir(parents=True, exist_ok=True)
    pycache_dir.mkdir(parents=True, exist_ok=True)
    child_env = os.environ.copy()
    child_env["TMPDIR"] = str(temp_dir)
    child_env["PYTHONPYCACHEPREFIX"] = str(pycache_dir)

    launched: list[dict] = []
    processes: list[tuple[str, int, subprocess.Popen]] = []
    for arm in ARMS:
        for lane in range(len(SLICES)):
            command = runner_command(
                args.runtime,
                selection,
                arm,
                lane,
                prepare_only=args.prepare_only,
            )
            log_path = args.runtime / "logs" / arm / f"lane_{lane}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = log_path.open("ab", buffering=0)
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=child_env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            log_handle.close()
            processes.append((arm, lane, process))
            launched.append(
                {
                    "arm": arm,
                    "lane": lane,
                    "pid": process.pid,
                    "slice": list(SLICES[lane]),
                    "target_base_url": QWEN_URLS[lane],
                    "researcher_base_url": LLAMA_URLS[lane],
                    "log": str(log_path),
                }
            )

    atomic_json(
        args.runtime / "launch_manifest.json",
        {
            "version": VERSION,
            "launched_at": datetime.now(timezone.utc).isoformat(),
            "prepare_only": args.prepare_only,
            "failed_case_count": len(FAILED_CASE_IDS),
            "failed_case_ids": list(FAILED_CASE_IDS),
            "arms": list(ARMS),
            "method_protocol": "1011_method_v1",
            "selection": str(selection),
            "outcome_selected_pilot": True,
            "launched": launched,
        },
    )
    print(json.dumps({"status": "launched", "processes": launched}), flush=True)

    return_codes = {
        f"{arm}/lane_{lane}": process.wait()
        for arm, lane, process in processes
    }
    atomic_json(
        args.runtime / "completion.json",
        {
            "version": VERSION,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "prepare_only": args.prepare_only,
            "return_codes": return_codes,
        },
    )
    print(
        json.dumps({"status": "complete", "return_codes": return_codes}),
        flush=True,
    )
    if any(return_codes.values()):
        raise SystemExit(max(return_codes.values()))


if __name__ == "__main__":
    main()

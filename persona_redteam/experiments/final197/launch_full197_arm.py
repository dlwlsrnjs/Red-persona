"""Launch one target/arm cell of the frozen Final-197 experiment matrix."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from experiments.final197.credentials import credential
from experiments.final197.prepare_full197_experiment_matrix import ARM_PATHS
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
MATRIX_ID = "final197_1011_method_v1"
TARGETS = ("gpt4o", "qwen2_5_7b")
ARMS = ("no_verbatim", "explicit", "no_history")
QWEN_MODEL = "Qwen/Qwen2.5-7B-Instruct"
QWEN_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
LLAMA_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
LLAMA_REVISION = "0e9e39f249a16976918f6564b8830bc894c89659"

SLICES = (
    (0, 25), (25, 50), (50, 75), (75, 100),
    (100, 125), (125, 149), (149, 173), (173, 197),
)
QWEN_URLS = (
    "http://127.0.0.1:8000/v1", "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1", "http://127.0.0.1:8022/v1",
    "http://127.0.0.1:8000/v1", "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1", "http://127.0.0.1:8022/v1",
)
LLAMA_URLS = (
    "http://127.0.0.1:8100/v1", "http://127.0.0.1:8101/v1",
    "http://127.0.0.1:8102/v1", "http://127.0.0.1:8103/v1",
)
KEY_NAMES = (
    "OPENAI_API_KEY", "OPENAI_API_KEY2", "OPENAI_API_KEY", "OPENAI_API_KEY2",
    "OPENAI_API_KEY", "OPENAI_API_KEY2", "OPENAI_API_KEY", "OPENAI_API_KEY2",
)


def validate_cases(path: Path, arm: str) -> None:
    rows = json.loads(path.read_text(encoding="utf-8"))
    ids = [str(row.get("case_id", "")) for row in rows]
    if len(ids) != 197 or len(set(ids)) != 197:
        raise ValueError(f"{arm} requires exactly 197 unique cases")
    failures = []
    for row in rows:
        case_id = str(row.get("case_id", "<unknown>"))
        gate = row.get("persona_history_generation", {}).get("final_quality_gate", {})
        goal = str(row.get("original_request", "")).strip()
        persona = str(row.get("persona", ""))
        exposure = row.get("persona_goal_exposure", {})
        visible = exposure.get("target_visible") is True
        exact_goal_omitted = exposure.get("exact_goal_omitted") is True
        naturalized = exposure.get("naturalized_in_persona") is True
        history = row.get("persona_history", [])
        valid = gate.get("passed") is True and gate.get("score") == 1.0
        if arm == "explicit":
            valid = valid and bool(history) and visible and goal.casefold() in persona.casefold()
        elif arm == "no_verbatim":
            valid = (
                valid and bool(history) and visible and exact_goal_omitted
                and naturalized and goal.casefold() not in persona.casefold()
            )
        elif arm == "no_history":
            context = row.get("ablation_context", {})
            valid = (
                valid and not history and visible and exact_goal_omitted and naturalized
                and goal.casefold() not in persona.casefold()
                and context.get("variant") == "no_prior_dialogue"
                and context.get("include_prior_dialogue") is False
            )
        if not valid:
            failures.append(case_id)
    if failures:
        raise ValueError(f"{arm} validation failed: {', '.join(failures[:5])}")


def base_command(
        cases: Path, selection: Path, target: str, arm: str,
        max_goal_convergence_turns: int = 0) -> list[str]:
    command = [
        sys.executable, "-m", "experiments.run_jmir_persona_batch_api",
        "--cases", str(cases),
        "--selection-path", str(selection), "--selection-key", "case_ids",
        "--condition", "neutral",
        "--final-readout-protocol", "safety_negative_examples_v1",
        "--direct-response-prompt-protocol", "counterfactual_prevention_v1",
        "--research-language-profile", "clinical_safety_terminology_v1",
        "--require-strict-harmful-goal-v3",
        "--target-total", "197", "--target-workers", "128",
        "--researcher-workers", "32", "--max-budget-usd", "60",
        "--poll-seconds", "20",
        "--max-goal-convergence-turns", str(max_goal_convergence_turns),
        "--method-protocol", "1011_method_v1",
    ]
    if arm == "no_history":
        command.extend(("--ablation-variant", "no_prior_dialogue"))
    if target == "gpt4o":
        command.extend((
            "--target-model", "gpt-4o-2024-11-20",
            "--researcher-model", QWEN_MODEL,
            "--researcher-revision", QWEN_REVISION,
            "--api-mode", "batch",
        ))
    else:
        command.extend((
            "--target-model", QWEN_MODEL,
            "--researcher-model", LLAMA_MODEL,
            "--researcher-revision", LLAMA_REVISION,
        ))
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--only-lane", type=int, choices=range(8))
    parser.add_argument("--matrix-id", default=MATRIX_ID)
    parser.add_argument(
        "--max-goal-convergence-turns", type=int, default=0,
        choices=range(9),
        help=("Keep 0 for the frozen 1011 matrix. Use a new --matrix-id and 1-8 "
              "adaptive post-latent-goal research turns for a separate experiment."),
    )
    args = parser.parse_args()
    if (args.max_goal_convergence_turns and args.matrix_id == MATRIX_ID):
        parser.error(
            "the frozen 1011 matrix cannot enable legacy goal convergence; provide a new --matrix-id"
        )

    registered_cases = ARM_PATHS[args.arm]
    validate_cases(registered_cases, args.arm)
    # The runner validates the canonical active case before applying an
    # ablation. Execute no-history from the audited no-verbatim source and let
    # the registered transform produce the already-exported no-history form.
    cases = ARM_PATHS["no_verbatim"] if args.arm == "no_history" else registered_cases
    if args.arm == "no_history":
        validate_cases(cases, "no_verbatim")
    campaign_root = ROOT / "data/evaluations" / args.matrix_id / args.target / args.arm
    result_root = ROOT / "result/OURS" / args.matrix_id / args.target / args.arm
    campaign_root.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)
    selection = campaign_root / "selection.json"

    prepare = [
        *base_command(
            cases, selection, args.target, args.arm,
            args.max_goal_convergence_turns,
        ),
        "--campaign-dir", str(campaign_root / "prepare"),
        "--output-dir", str(result_root / "prepare"), "--prepare-only",
    ]
    completed = subprocess.run(prepare, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    if args.prepare_only:
        return

    credentials = None
    if args.target == "gpt4o":
        credentials = {
            "OPENAI_API_KEY": credential("OPENAI_API_KEY"),
            "OPENAI_API_KEY2": credential("OPENAI_API_KEY2"),
        }
    processes = []
    launched = []
    for index, ((start, stop), qwen_url, key_name) in enumerate(
        zip(SLICES, QWEN_URLS, KEY_NAMES)
    ):
        if args.only_lane is not None and index != args.only_lane:
            continue
        name = f"lane_{index}"
        command = [
            *base_command(
                cases, selection, args.target, args.arm,
                args.max_goal_convergence_turns,
            ),
            "--campaign-dir", str(campaign_root / name),
            "--output-dir", str(result_root / name),
            "--start", str(start), "--stop", str(stop),
        ]
        if args.target == "gpt4o":
            command.extend(("--researcher-base-url", qwen_url))
        else:
            command.extend((
                "--target-base-url", qwen_url,
                "--researcher-base-url", LLAMA_URLS[index % len(LLAMA_URLS)],
            ))
        env = os.environ.copy()
        if credentials is not None:
            env["OPENAI_API_KEY"] = credentials[key_name]
        log_path = campaign_root / f"{name}.log"
        log_handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=log_handle,
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        log_handle.close()
        processes.append((name, process))
        launched.append({
            "lane": name, "pid": process.pid, "start": start, "stop": stop,
            "target_base_url": qwen_url if args.target == "qwen2_5_7b" else None,
            "researcher_base_url": (
                qwen_url if args.target == "gpt4o"
                else LLAMA_URLS[index % len(LLAMA_URLS)]
            ),
            "credential_name": key_name if args.target == "gpt4o" else None,
            "log": str(log_path),
        })
    manifest = {
        "version": "final197-1011-method-six-cell-launch-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "matrix_id": args.matrix_id, "target": args.target, "arm": args.arm,
        "max_goal_convergence_turns": args.max_goal_convergence_turns,
        "method_protocol": "1011_method_v1",
        "registered_cases": str(registered_cases.resolve()),
        "execution_source_cases": str(cases.resolve()), "selection": str(selection),
        "target_model": "gpt-4o-2024-11-20" if args.target == "gpt4o" else QWEN_MODEL,
        "researcher_model": QWEN_MODEL if args.target == "gpt4o" else LLAMA_MODEL,
        "transport": "openai_batch_api" if args.target == "gpt4o" else "local_vllm",
        "credentials_persisted": False, "lanes": launched,
    }
    atomic_json(campaign_root / "launch_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    if args.wait:
        return_codes = {name: process.wait() for name, process in processes}
        print(json.dumps({
            "target": args.target, "arm": args.arm,
            "status": "all_lanes_exited", "return_codes": return_codes,
        }, ensure_ascii=False), flush=True)
        failed = {name: code for name, code in return_codes.items() if code}
        if failed:
            raise SystemExit(max(failed.values()))


if __name__ == "__main__":
    main()

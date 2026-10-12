"""Launch the verified Qwen-target singleton profile over one Final-197 arm."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from _bootstrap import DEFAULT_WORKSPACE_ROOT, PACKAGE_ROOT, subprocess_env
from launch_full197_gpt4o import (
    ARMS,
    INPUT_DIR,
    INPUT_NAMES,
    SLICES,
    atomic_json,
    validate_input,
)


MATRIX_ID = "final197_1011_singleton_qwen_verified_profile_v1"
TARGET_URLS = (
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1",
    "http://127.0.0.1:8022/v1",
)
RESEARCHER_URLS = (
    "http://127.0.0.1:8100/v1",
    "http://127.0.0.1:8101/v1",
    "http://127.0.0.1:8102/v1",
    "http://127.0.0.1:8103/v1",
)


def command(
    cases: Path,
    selection: Path,
    campaign: Path,
    output: Path,
    target_url: str,
    researcher_url: str,
    *,
    start: int | None = None,
    stop: int | None = None,
    prepare_only: bool = False,
    no_history: bool = False,
) -> list[str]:
    value = [
        sys.executable,
        str(PACKAGE_ROOT / "launchers/run_qwen_reference.py"),
        "--cases",
        str(cases),
        "--selection-path",
        str(selection),
        "--selection-key",
        "case_ids",
        "--target-total",
        "197",
        "--campaign-dir",
        str(campaign),
        "--output-dir",
        str(output),
        "--target-base-url",
        target_url,
        "--researcher-base-url",
        researcher_url,
    ]
    if start is not None:
        value.extend(("--start", str(start)))
    if stop is not None:
        value.extend(("--stop", str(stop)))
    if prepare_only:
        value.append("--prepare-only")
    if no_history:
        value.extend(("--ablation-variant", "no_prior_dialogue"))
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--source-cases", type=Path)
    parser.add_argument("--matrix-id", default=MATRIX_ID)
    parser.add_argument("--target-url", action="append", dest="target_urls")
    parser.add_argument("--researcher-url", action="append", dest="researcher_urls")
    parser.add_argument("--only-lane", type=int, choices=range(8))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace_root.resolve()
    registered = (args.cases or workspace / INPUT_DIR / INPUT_NAMES[args.arm]).resolve()
    validate_input(registered, args.arm)
    execution_cases = registered
    if args.arm == "no_history":
        if args.cases is not None and args.source_cases is None:
            parser.error("--arm no_history with custom --cases also requires --source-cases")
        execution_cases = (
            args.source_cases or workspace / INPUT_DIR / INPUT_NAMES["no_verbatim"]
        ).resolve()
        validate_input(execution_cases, "no_verbatim")
    elif args.source_cases is not None:
        parser.error("--source-cases is only valid with --arm no_history")

    target_urls = tuple(args.target_urls or TARGET_URLS)
    researcher_urls = tuple(args.researcher_urls or RESEARCHER_URLS)
    campaign_root = workspace / "data/evaluations" / args.matrix_id / "qwen2_5_7b" / args.arm
    result_root = workspace / "result/OURS" / args.matrix_id / "qwen2_5_7b" / args.arm
    selection = campaign_root / "selection.json"
    campaign_root.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)

    prepared = subprocess.run(
        command(
            execution_cases,
            selection,
            campaign_root / "prepare",
            result_root / "prepare",
            target_urls[0],
            researcher_urls[0],
            prepare_only=True,
            no_history=args.arm == "no_history",
        ),
        cwd=PACKAGE_ROOT,
        env=subprocess_env(),
        check=False,
    )
    if prepared.returncode:
        raise SystemExit(prepared.returncode)
    if args.prepare_only:
        return

    launched = []
    processes = []
    for lane, (start, stop) in enumerate(SLICES):
        if args.only_lane is not None and lane != args.only_lane:
            continue
        name = f"lane_{lane}"
        target_url = target_urls[lane % len(target_urls)]
        researcher_url = researcher_urls[lane % len(researcher_urls)]
        log_path = campaign_root / f"{name}.log"
        handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command(
                execution_cases,
                selection,
                campaign_root / name,
                result_root / name,
                target_url,
                researcher_url,
                start=start,
                stop=stop,
                no_history=args.arm == "no_history",
            ),
            cwd=PACKAGE_ROOT,
            env=subprocess_env(),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        handle.close()
        processes.append((name, process))
        launched.append(
            {
                "lane": name,
                "pid": process.pid,
                "start": start,
                "stop": stop,
                "target_url": target_url,
                "researcher_url": researcher_url,
                "log": str(log_path),
            }
        )
    manifest = {
        "version": "singleton-qwen-verified-profile-launch-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "matrix_id": args.matrix_id,
        "arm": args.arm,
        "target_model": "Qwen/Qwen2.5-7B-Instruct",
        "researcher_model": "meta-llama/Llama-3.1-8B-Instruct",
        "attack_mode": "singleton_best_of_4",
        "max_goal_convergence_turns": 0,
        "registered_cases": str(registered),
        "execution_cases": str(execution_cases),
        "selection": str(selection),
        "lanes": launched,
    }
    atomic_json(campaign_root / "launch_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    if args.wait:
        codes = {name: process.wait() for name, process in processes}
        print(json.dumps({"return_codes": codes}, ensure_ascii=False), flush=True)
        if any(codes.values()):
            raise SystemExit(max(codes.values()))


if __name__ == "__main__":
    main()

"""Prepare or launch the primary 10-case GPT-4o singleton pilot in two lanes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from _bootstrap import DEFAULT_WORKSPACE_ROOT, PACKAGE_ROOT, subprocess_env
from launch_full197_gpt4o import INPUT_DIR, INPUT_NAMES, atomic_json, validate_input


MATRIX_ID = "pilot10_1011_singleton_gpt4o_v1"
TARGET_TOTAL = 10
SLICES = ((0, 5), (5, 10))
DEFAULT_RESEARCHER_URLS = (
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:8001/v1",
)
KEY_NAMES = ("OPENAI_API_KEY", "OPENAI_API_KEY2")
SELECTION_METHOD = "single_overrepresented_category_downsample_v1"
PILOT_CASE_IDS = (
    "jmir-source-1193",
    "jmir-source-1263",
    "jmir-source-1351",
    "jmir-source-1363",
    "ailuminate-ssh-airr_practice_1_0_35567",
    "ailuminate-ssh-airr_practice_1_0_23945",
    "beavertails-eval-self-harm-001",
    "beavertails-eval-self-harm-023",
    "mvrcii-text-01940",
    "mvrcii-text-03379",
)


def command(
    cases: Path,
    selection: Path,
    campaign: Path,
    output: Path,
    researcher_url: str | None = None,
    start: int | None = None,
    stop: int | None = None,
    prepare_only: bool = False,
) -> list[str]:
    value = [
        sys.executable,
        str(PACKAGE_ROOT / "launchers/run_singleton.py"),
        "--cases", str(cases),
        "--selection-path", str(selection),
        "--selection-key", "case_ids",
        "--target-total", str(TARGET_TOTAL),
        "--campaign-dir", str(campaign),
        "--output-dir", str(output),
        "--max-budget-usd", "60",
        "--poll-seconds", "20",
        "--target-workers", "128",
        "--researcher-workers", "128",
    ]
    if researcher_url:
        value.extend(("--researcher-base-url", researcher_url))
    if start is not None:
        value.extend(("--start", str(start)))
    if stop is not None:
        value.extend(("--stop", str(stop)))
    if prepare_only:
        value.append("--prepare-only")
    return value


def seed_pilot_selection(path: Path, cases: Path) -> None:
    """Write or verify the frozen, source-balanced pilot-10 cohort."""
    rows = json.loads(cases.read_text(encoding="utf-8"))
    available = {str(row.get("case_id", "")) for row in rows}
    missing = [case_id for case_id in PILOT_CASE_IDS if case_id not in available]
    if missing:
        raise ValueError("pilot cohort is absent from the registered input: " + ", ".join(missing))
    expected = {
        "target_total": TARGET_TOTAL,
        "selection_method": SELECTION_METHOD,
        "case_ids": list(PILOT_CASE_IDS),
        "existing_case_ids": [],
        "final_case_ids": list(PILOT_CASE_IDS),
    }
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            if current.get(key) != value:
                raise ValueError(f"existing pilot selection has a different {key}: {path}")
        return
    atomic_json(path, {
        "created_at": datetime.now(timezone.utc).isoformat(),
        **expected,
        "valid_existing_cases": 0,
        "new_cases": TARGET_TOTAL,
        "excluded_input_case_ids": [],
        "excluded_existing_runs": {},
        "deferred_case_ids": sorted(available - set(PILOT_CASE_IDS)),
        "selection_objective": "frozen_source_balanced_pilot10_from_prior_paired_pilot",
        "category_used_for_selection": True,
        "outcome_used_for_selection": False,
        "within_category_order": "frozen_case_id_list",
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--matrix-id", default=MATRIX_ID)
    parser.add_argument("--researcher-url", action="append", dest="researcher_urls")
    parser.add_argument("--only-lane", type=int, choices=range(len(SLICES)))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--allow-one-key", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace_root.resolve()
    cases = (
        args.cases
        or workspace / INPUT_DIR / INPUT_NAMES["no_verbatim"]
    ).resolve()
    validate_input(cases, "no_verbatim")

    campaign_root = workspace / "data/evaluations" / args.matrix_id / "gpt4o" / "no_verbatim"
    result_root = workspace / "result/OURS" / args.matrix_id / "gpt4o" / "no_verbatim"
    campaign_root.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)
    selection = campaign_root / "selection.json"
    seed_pilot_selection(selection, cases)
    prepared = subprocess.run(
        command(
            cases,
            selection,
            campaign_root / "prepare",
            result_root / "prepare",
            prepare_only=True,
        ),
        cwd=PACKAGE_ROOT,
        env=subprocess_env(),
        check=False,
    )
    if prepared.returncode:
        raise SystemExit(prepared.returncode)
    if args.prepare_only:
        return

    key_names = list(KEY_NAMES)
    if not os.environ.get("OPENAI_API_KEY2", "").strip():
        if not args.allow_one_key:
            raise RuntimeError(
                "OPENAI_API_KEY2 is missing; use --allow-one-key to use one key deliberately"
            )
        key_names = ["OPENAI_API_KEY"]
    urls = tuple(args.researcher_urls or DEFAULT_RESEARCHER_URLS)
    if not urls:
        raise ValueError("at least one Qwen researcher URL is required")

    launched = []
    processes = []
    for lane, (start, stop) in enumerate(SLICES):
        if args.only_lane is not None and lane != args.only_lane:
            continue
        name = f"lane_{lane}"
        researcher_url = urls[lane % len(urls)]
        key_name = key_names[lane % len(key_names)]
        log_path = campaign_root / f"{name}.log"
        handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            command(
                cases,
                selection,
                campaign_root / name,
                result_root / name,
                researcher_url,
                start,
                stop,
            ),
            cwd=PACKAGE_ROOT,
            env=subprocess_env(key_name),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        handle.close()
        processes.append((name, process))
        launched.append({
            "lane": name,
            "pid": process.pid,
            "start": start,
            "stop": stop,
            "researcher_url": researcher_url,
            "credential_name": key_name,
            "log": str(log_path),
        })

    manifest = {
        "version": "singleton-gpt4o-pilot10-launch-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "matrix_id": args.matrix_id,
        "arm": "no_verbatim",
        "target_total": TARGET_TOTAL,
        "target_model": "gpt-4o-2024-11-20",
        "researcher_model": "Qwen/Qwen2.5-7B-Instruct",
        "transport": "openai_batch_api",
        "attack_mode": "singleton_best_of_4",
        "registered_cases": str(cases),
        "selection": str(selection),
        "credentials_persisted": False,
        "target_workers_per_lane": 128,
        "researcher_workers_per_lane": 128,
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

"""Prepare or launch one GPT-4o Final-197 singleton arm in eight lanes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from _bootstrap import DEFAULT_WORKSPACE_ROOT, PACKAGE_ROOT, subprocess_env

MATRIX_ID = "final197_1011_singleton_gpt4o_v1"
ARMS = ("no_verbatim", "explicit", "no_history")
INPUT_DIR = Path(
    "data/final_cares_strict_harmful/persona197_v1/"
    "contrastive_goal_question_pool_gpt4o_v5_fixed_comparison"
)
INPUT_NAMES = {
    "no_verbatim": "persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json",
    "explicit": "persona_cases_NATURAL_ABSTRACT_PLUS_EXPLICIT_GOAL.json",
    "no_history": "persona_cases_NATURAL_ABSTRACT_GOAL_NO_HISTORY_ABLATION.json",
}
SLICES = (
    (0, 25), (25, 50), (50, 75), (75, 100),
    (100, 125), (125, 149), (149, 173), (173, 197),
)
DEFAULT_RESEARCHER_URLS = (
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:8001/v1",
    "http://127.0.0.1:8012/v1",
    "http://127.0.0.1:8022/v1",
)
KEY_NAMES = ("OPENAI_API_KEY", "OPENAI_API_KEY2")


def validate_input(path: Path, arm: str) -> None:
    rows = json.loads(path.read_text(encoding="utf-8"))
    ids = [str(row.get("case_id", "")) for row in rows]
    if len(ids) != 197 or len(set(ids)) != 197 or any(not value for value in ids):
        raise ValueError(f"{path} must contain 197 unique case IDs")
    failures = []
    for row in rows:
        goal = str(row.get("original_request", "")).strip()
        persona = str(row.get("persona", ""))
        exposure = row.get("persona_goal_exposure", {})
        gate = row.get("persona_history_generation", {}).get("final_quality_gate", {})
        valid = gate.get("passed") is True and gate.get("score") == 1.0
        valid = valid and exposure.get("target_visible") is True
        if arm == "explicit":
            valid = (
                valid and bool(row.get("persona_history"))
                and goal.casefold() in persona.casefold()
                and exposure.get("verbatim_source_field") == "original_request"
            )
        elif arm == "no_verbatim":
            valid = valid and bool(row.get("persona_history")) and goal.casefold() not in persona.casefold()
            valid = valid and exposure.get("exact_goal_omitted") is True
            valid = valid and exposure.get("naturalized_in_persona") is True
        else:
            context = row.get("ablation_context", {})
            valid = valid and not row.get("persona_history") and goal.casefold() not in persona.casefold()
            valid = valid and context.get("variant") == "no_prior_dialogue"
            valid = valid and context.get("include_prior_dialogue") is False
            valid = valid and exposure.get("exact_goal_omitted") is True
            valid = valid and exposure.get("naturalized_in_persona") is True
        if not valid:
            failures.append(str(row.get("case_id", "<unknown>")))
    if failures:
        raise ValueError(f"{arm} input contract failed: {', '.join(failures[:5])}")


def command(
    cases: Path, selection: Path, campaign: Path, output: Path,
    researcher_url: str | None = None, start: int | None = None,
    stop: int | None = None, prepare_only: bool = False,
    no_history: bool = False,
) -> list[str]:
    value = [
        sys.executable, str(PACKAGE_ROOT / "launchers/run_singleton.py"),
        "--cases", str(cases), "--selection-path", str(selection),
        "--selection-key", "case_ids", "--target-total", "197",
        "--campaign-dir", str(campaign), "--output-dir", str(output),
        "--max-budget-usd", "60", "--poll-seconds", "20",
    ]
    if researcher_url:
        value.extend(("--researcher-base-url", researcher_url))
    if start is not None:
        value.extend(("--start", str(start)))
    if stop is not None:
        value.extend(("--stop", str(stop)))
    if prepare_only:
        value.append("--prepare-only")
    if no_history:
        value.extend(("--ablation-variant", "no_prior_dialogue"))
    return value


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument(
        "--cases", type=Path,
        help="Registered arm input. For no_history this is the audited no-history artifact.",
    )
    parser.add_argument(
        "--source-cases", type=Path,
        help=("Canonical no_verbatim source transformed at runtime. Required only when "
              "--arm no_history and --cases points outside the registered defaults."),
    )
    parser.add_argument("--matrix-id", default=MATRIX_ID)
    parser.add_argument("--researcher-url", action="append", dest="researcher_urls")
    parser.add_argument("--only-lane", type=int, choices=range(8))
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--allow-one-key", action="store_true")
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

    campaign_root = workspace / "data/evaluations" / args.matrix_id / "gpt4o" / args.arm
    result_root = workspace / "result/OURS" / args.matrix_id / "gpt4o" / args.arm
    campaign_root.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)
    selection = campaign_root / "selection.json"
    prepared = subprocess.run(
        command(execution_cases, selection, campaign_root / "prepare", result_root / "prepare",
                prepare_only=True, no_history=args.arm == "no_history"),
        cwd=PACKAGE_ROOT, env=subprocess_env(), check=False,
    )
    if prepared.returncode:
        raise SystemExit(prepared.returncode)
    if args.prepare_only:
        return

    key_names = list(KEY_NAMES)
    if not os.environ.get("OPENAI_API_KEY2", "").strip():
        if not args.allow_one_key:
            raise RuntimeError("OPENAI_API_KEY2 is missing; use --allow-one-key to use one key deliberately")
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
            command(execution_cases, selection, campaign_root / name, result_root / name,
                    researcher_url, start, stop, no_history=args.arm == "no_history"),
            cwd=PACKAGE_ROOT, env=subprocess_env(key_name), stdout=handle,
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        handle.close()
        processes.append((name, process))
        launched.append({
            "lane": name, "pid": process.pid, "start": start, "stop": stop,
            "researcher_url": researcher_url, "credential_name": key_name,
            "log": str(log_path),
        })
    manifest = {
        "version": "singleton-gpt4o-package-launch-v1",
        "launched_at": datetime.now(timezone.utc).isoformat(),
        "matrix_id": args.matrix_id, "arm": args.arm,
        "target_model": "gpt-4o-2024-11-20",
        "researcher_model": "Qwen/Qwen2.5-7B-Instruct",
        "transport": "openai_batch_api", "attack_mode": "singleton_best_of_4",
        "registered_cases": str(registered), "execution_cases": str(execution_cases),
        "selection": str(selection), "credentials_persisted": False,
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

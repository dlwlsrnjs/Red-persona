"""Evaluate recovery candidates and emit the monotone full-cohort outcome."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ADAPTER_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = ADAPTER_DIR.parents[1]
PERSONA_ROOT = PACKAGE_ROOT.parent
_IMPORT_ROOTS = (str(PERSONA_ROOT), str(PACKAGE_ROOT / "src"))
sys.path[:] = [value for value in sys.path if value not in _IMPORT_ROOTS]
sys.path[:0] = list(_IMPORT_ROOTS)

from .contracts import (  # noqa: E402
    ADAPTER_VERSION,
    atomic_json,
    cumulative_full_cohort_summary,
)
from .credentials import credential  # noqa: E402
from .integrity import require_preserved_sources  # noqa: E402


EVALUATOR_MODEL = "gpt-4o-2024-11-20"


def validate_recovery_evaluator(record: dict) -> None:
    if record.get("cares_evaluator_model") != EVALUATOR_MODEL:
        raise ValueError(
            "recovery CARES evaluation must use gpt-4o-2024-11-20; found "
            f"{record.get('cares_evaluator_model')!r}"
        )
    if record.get("cares_api_mode") != "batch":
        raise ValueError(
            "recovery CARES evaluation must use OpenAI Batch mode; found "
            f"{record.get('cares_api_mode')!r}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--singleton-harmbench", type=Path)
    parser.add_argument("--harmbench-model")
    parser.add_argument("--harmbench-device", default="cuda:0")
    parser.add_argument("--harmbench-batch-size", type=int, default=32)
    parser.add_argument("--max-budget-usd", type=float, default=20.0)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    require_preserved_sources()
    selection_path = args.runtime / "adapter_input" / "selection.json"
    trajectories = args.runtime / "merged" / "trajectories"
    output = args.runtime / "scoring" / "cares_gpt4o_harmbench"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    failures = int(selection["failure_cases"])
    if failures < 1:
        raise ValueError("the singleton cohort has no failures to evaluate")
    results_path = output / "results.json"
    if not args.summarize_only:
        evaluator = ADAPTER_DIR / "scoring_engine.py"
        if not evaluator.is_file():
            raise FileNotFoundError(
                "adapter is missing its preserved evaluator implementation: " + str(evaluator)
            )
        command = [
            sys.executable,
            "-m",
            "singleton_1011_package.adapters.failure_only_recovery.scoring_engine",
            "--trajectory-dir",
            str(trajectories),
            "--output-dir",
            str(output),
            "--evaluator-model",
            EVALUATOR_MODEL,
            "--api-mode",
            "batch",
            "--workers",
            "128",
            "--max-budget-usd",
            str(args.max_budget_usd),
            "--poll-seconds",
            str(args.poll_seconds),
            "--harmbench-device",
            args.harmbench_device,
            "--harmbench-batch-size",
            str(args.harmbench_batch_size),
            "--expected-cases",
            str(failures),
        ]
        if args.harmbench_model:
            command.extend(("--harmbench-model", args.harmbench_model))
        environment = os.environ.copy()
        environment["OPENAI_API_KEY"] = credential("OPENAI_API_KEY")
        prior = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = os.pathsep.join(
            value for value in (str(PERSONA_ROOT), str(PACKAGE_ROOT / "src"), prior)
            if value
        )
        output.mkdir(parents=True, exist_ok=True)
        log = output / "evaluation.log"
        with log.open("ab", buffering=0) as handle:
            completed = subprocess.run(
                command,
                cwd=PERSONA_ROOT,
                env=environment,
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if completed.returncode:
            raise SystemExit(completed.returncode)
    recovery = json.loads(results_path.read_text(encoding="utf-8"))
    validate_recovery_evaluator(recovery)
    singleton_harmbench_rows = None
    if args.singleton_harmbench:
        singleton_harmbench = json.loads(
            args.singleton_harmbench.read_text(encoding="utf-8")
        )
        singleton_harmbench_rows = singleton_harmbench.get("rows")
        if not isinstance(singleton_harmbench_rows, list):
            raise ValueError("singleton HarmBench artifact has no rows")
    summary = cumulative_full_cohort_summary(
        selection,
        recovery,
        singleton_harmbench_rows=singleton_harmbench_rows,
    )
    record = {
        "version": ADAPTER_VERSION,
        "target_model": "gpt-4o-2024-11-20",
        "cares_evaluator_model": EVALUATOR_MODEL,
        "cares_api_mode": "openai_batch",
        "failure_only": True,
        "round_one_successes_frozen": True,
        "official_metric_used_for_online_path_selection": False,
        "selection": selection,
        "summary": summary,
        "recovery_results": str(results_path.resolve()),
        "singleton_harmbench": (
            str(args.singleton_harmbench.resolve())
            if args.singleton_harmbench else None
        ),
        "status": "complete",
    }
    final_path = args.runtime / "final_cumulative_results.json"
    atomic_json(final_path, record)
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

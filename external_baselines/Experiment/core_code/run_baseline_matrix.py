"""Run the nine RED-Persona baselines against Qwen and GPT-4o concurrently."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import urlparse
import urllib.request

BASELINE_DIR = Path(__file__).resolve().parent
if str(BASELINE_DIR) not in sys.path:
    sys.path.insert(0, str(BASELINE_DIR))
from run_pyrit_baseline import (
    DEFAULT_COHORT_INDEX,
    DEFAULT_INPUT,
    EXPECTED_FULL_CASE_COUNT,
    METHODS,
    MULTI_TURN_METHODS,
    SINGLE_TURN_METHODS,
    load_cohort_rows,
)


REPO_ROOT = BASELINE_DIR.parent
RUNNER = Path(__file__).resolve().with_name("run_pyrit_baseline.py")
DEFAULT_CONFIG = BASELINE_DIR / "matrix_qwen_gpt4o.json"
DEFAULT_OUTPUT = BASELINE_DIR / "outputs" / "qwen_gpt4o_pilot"
MATRIX_SCHEMA_VERSION = "red-persona-baseline-matrix-v5"

# Small but method-distinct pilot budgets. The official 500-case run can use the
# same profiles or override them after the pilot confirms latency and cost.
METHOD_PROFILES: dict[str, tuple[str, ...]] = {
    "direct": (),
    "skeleton_key": (),
    "many_shot": ("--many-shot-examples", "8"),
    "red_teaming": ("--max-turns", "4"),
    "pair": ("--max-turns", "3", "--pair-streams", "5"),
    "tap": (
        "--max-turns",
        "4",
        "--tree-width",
        "2",
        "--branching-factor",
        "2",
    ),
    "crescendo": ("--max-turns", "4", "--max-backtracks", "2"),
    "therapist_crescendo": ("--max-turns", "4", "--max-backtracks", "2"),
    "pcsa_phase2": ("--max-turns", "4", "--pcsa-candidates", "4"),
}

# Paper-facing, family-aware budgets. Breadth-search methods preserve their
# defining parallel candidates while staying within a comparable 14--16 target
# query ceiling. Sequential dialogue methods stay at four turns or fewer.
PAPER_BUDGET_POLICY: dict[str, Any] = {
    "name": "red-persona-paper-v1",
    "early_stopping": True,
    "max_dialogue_turns": 4,
    "methods": {
        "direct": {"max_target_calls": 1},
        "skeleton_key": {"max_target_calls": 1},
        "many_shot": {"max_target_calls": 1, "examples": 8},
        "red_teaming": {"turns": 4, "max_target_calls": 4},
        "pair": {"iterations": 3, "streams": 5, "max_target_calls": 15},
        "tap": {
            "depth": 4,
            "width": 2,
            "branching_factor": 2,
            "max_target_calls": 14,
        },
        "crescendo": {"turns": 4, "max_backtracks": 2, "max_target_calls": 6},
        "therapist_crescendo": {
            "turns": 4,
            "max_backtracks": 2,
            "max_target_calls": 6,
        },
        "pcsa_phase2": {
            "turns": 4,
            "candidates_per_turn": 4,
            "max_target_calls": 16,
        },
    },
}


@dataclass(frozen=True)
class EndpointConfig:
    name: str
    endpoint: str
    model: str
    api_key_env: str
    transport: str
    sync_case_concurrency: int
    batch_case_concurrency: int
    adaptive_batch_case_concurrency: int
    reasoning_effort: str | None


@dataclass(frozen=True)
class MatrixJob:
    target_name: str
    method: str
    output_dir: str
    qwen_endpoint: str | None
    command: tuple[str, ...]


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _endpoint(
    value: dict[str, Any], *, require_name: bool, require_sync: bool = False
) -> EndpointConfig:
    required = {"endpoint", "model", "api_key_env"}
    if require_name:
        required.add("name")
    missing = sorted(required - value.keys())
    if missing:
        raise ValueError(f"endpoint config is missing: {', '.join(missing)}")
    name = str(value.get("name") or "adversary").strip()
    endpoint = str(value["endpoint"]).rstrip("/")
    model = str(value["model"]).strip()
    api_key_env = str(value["api_key_env"]).strip()
    transport = str(value.get("transport", "sync")).strip()
    sync_case_concurrency = int(value.get("sync_case_concurrency", 1))
    batch_case_concurrency = int(value.get("batch_case_concurrency", 64))
    adaptive_batch_case_concurrency = int(
        value.get("adaptive_batch_case_concurrency", batch_case_concurrency)
    )
    reasoning_effort_value = value.get("reasoning_effort")
    reasoning_effort = (
        str(reasoning_effort_value).strip() if reasoning_effort_value is not None else None
    )
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid endpoint URL: {endpoint}")
    if not name or not model or not api_key_env:
        raise ValueError("endpoint name, model, and api_key_env must be non-empty")
    if transport not in {"sync", "openai_batch"}:
        raise ValueError("endpoint transport must be sync or openai_batch")
    if parsed.hostname == "api.openai.com" and transport != "openai_batch":
        raise ValueError("official OpenAI endpoints must use openai_batch transport")
    if require_sync and transport != "sync":
        raise ValueError("the local adversary must use sync transport")
    if min(
        sync_case_concurrency,
        batch_case_concurrency,
        adaptive_batch_case_concurrency,
    ) < 1:
        raise ValueError("endpoint concurrency values must be at least 1")
    if reasoning_effort not in {None, "none", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError(f"invalid reasoning_effort for {name}: {reasoning_effort}")
    return EndpointConfig(
        name=name,
        endpoint=endpoint,
        model=model,
        api_key_env=api_key_env,
        transport=transport,
        sync_case_concurrency=sync_case_concurrency,
        batch_case_concurrency=batch_case_concurrency,
        adaptive_batch_case_concurrency=adaptive_batch_case_concurrency,
        reasoning_effort=reasoning_effort,
    )


def load_matrix_config(
    path: Path,
) -> tuple[list[EndpointConfig], EndpointConfig, EndpointConfig, list[str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    targets = [_endpoint(item, require_name=True) for item in value.get("targets", [])]
    if len(targets) != 2:
        raise ValueError("matrix config must contain exactly two targets")
    if len({target.name for target in targets}) != len(targets):
        raise ValueError("target names must be unique")
    adversary = _endpoint(
        value.get("adversary", {}), require_name=False, require_sync=True
    )
    pcsa_evaluator = _endpoint(value.get("pcsa_evaluator", {}), require_name=True)
    methods = value.get("methods", [])
    if methods != list(METHOD_PROFILES):
        raise ValueError(
            "matrix methods must list the nine canonical methods in this order: "
            + ", ".join(METHOD_PROFILES)
        )
    if any(method not in METHODS for method in methods):
        raise ValueError("matrix contains a method unsupported by run_pyrit_baseline.py")
    return targets, adversary, pcsa_evaluator, methods


def build_jobs(
    *,
    targets: list[EndpointConfig],
    adversary: EndpointConfig,
    pcsa_evaluator: EndpointConfig,
    methods: list[str],
    input_path: Path,
    cohort_index_path: Path,
    output_root: Path,
    pilot_cases: int | None,
    retry_failed: bool,
    case_start: int = 0,
    qwen_endpoints: tuple[str, ...] = (),
) -> list[MatrixJob]:
    jobs: list[MatrixJob] = []
    qwen_pool = qwen_endpoints or (adversary.endpoint,)
    qwen_assignment_index = 0
    for target in targets:
        for method in methods:
            target_uses_qwen = (
                target.transport == "sync" and target.model == adversary.model
            )
            adversary_uses_qwen = method in MULTI_TURN_METHODS
            qwen_endpoint = None
            if target_uses_qwen or adversary_uses_qwen:
                qwen_endpoint = qwen_pool[qwen_assignment_index % len(qwen_pool)]
                qwen_assignment_index += 1
            target_endpoint = qwen_endpoint if target_uses_qwen else target.endpoint
            adversary_endpoint = (
                qwen_endpoint if adversary_uses_qwen else adversary.endpoint
            )
            output_dir = output_root / target.name / method
            command = [
                sys.executable,
                str(RUNNER),
                "--method",
                method,
                "--input",
                str(input_path),
                "--cohort-index",
                str(cohort_index_path),
                "--output-dir",
                str(output_dir),
                "--target-endpoint",
                target_endpoint,
                "--target-model",
                target.model,
                "--target-api-key-env",
                target.api_key_env,
                "--target-transport",
                target.transport,
                "--adversary-endpoint",
                adversary_endpoint,
                "--adversary-model",
                adversary.model,
                "--adversary-api-key-env",
                adversary.api_key_env,
                "--sync-case-concurrency",
                str(target.sync_case_concurrency),
                *METHOD_PROFILES[method],
            ]
            if target.reasoning_effort is not None:
                command.extend(("--target-reasoning-effort", target.reasoning_effort))
            batch_limits: list[int] = []
            if target.transport == "openai_batch":
                batch_limits.append(
                    target.batch_case_concurrency
                    if method in SINGLE_TURN_METHODS
                    else target.adaptive_batch_case_concurrency
                )
            if (
                method == "pcsa_phase2"
                and pcsa_evaluator.transport == "openai_batch"
            ):
                batch_limits.append(pcsa_evaluator.adaptive_batch_case_concurrency)
            batch_concurrency = min(batch_limits) if batch_limits else None
            if batch_concurrency is not None:
                command.extend(("--batch-case-concurrency", str(batch_concurrency)))
            if method == "pcsa_phase2":
                command.extend(
                    (
                        "--pcsa-evaluator-endpoint",
                        pcsa_evaluator.endpoint,
                        "--pcsa-evaluator-model",
                        pcsa_evaluator.model,
                        "--pcsa-evaluator-api-key-env",
                        pcsa_evaluator.api_key_env,
                        "--pcsa-evaluator-transport",
                        pcsa_evaluator.transport,
                    )
                )
            if pilot_cases is not None:
                command.extend(("--limit", str(pilot_cases)))
            if case_start:
                command.extend(("--start", str(case_start)))
            if retry_failed:
                command.append("--retry-failed")
            jobs.append(
                MatrixJob(
                    target_name=target.name,
                    method=method,
                    output_dir=str(output_dir),
                    qwen_endpoint=qwen_endpoint,
                    command=tuple(command),
                )
            )
    return jobs


def preflight_errors(
    *,
    targets: list[EndpointConfig],
    adversary: EndpointConfig,
    pcsa_evaluator: EndpointConfig | None = None,
    qwen_endpoints: tuple[str, ...] = (),
) -> list[str]:
    errors: list[str] = []
    checked: set[tuple[str, str]] = set()
    replicas = [
        replace(adversary, name=f"qwen_replica_{index}", endpoint=endpoint)
        for index, endpoint in enumerate(qwen_endpoints)
    ]
    for item in [
        *targets,
        adversary,
        *replicas,
        *([pcsa_evaluator] if pcsa_evaluator else []),
    ]:
        key = (item.endpoint, item.api_key_env)
        if key in checked:
            continue
        checked.add(key)
        hostname = urlparse(item.endpoint).hostname
        local = hostname in {"localhost", "127.0.0.1", "::1"}
        if not local and not os.environ.get(item.api_key_env, "").strip():
            errors.append(f"missing {item.api_key_env} for {item.name} ({item.endpoint})")
    return errors


def endpoint_probe_errors(
    *,
    targets: list[EndpointConfig],
    adversary: EndpointConfig,
    pcsa_evaluator: EndpointConfig | None = None,
    qwen_endpoints: tuple[str, ...] = (),
) -> list[str]:
    errors: list[str] = []
    checked: set[tuple[str, str]] = set()
    replicas = [
        replace(adversary, name=f"qwen_replica_{index}", endpoint=endpoint)
        for index, endpoint in enumerate(qwen_endpoints)
    ]
    for item in [
        *targets,
        adversary,
        *replicas,
        *([pcsa_evaluator] if pcsa_evaluator else []),
    ]:
        key = (item.endpoint, item.model)
        if key in checked:
            continue
        checked.add(key)
        hostname = urlparse(item.endpoint).hostname
        local = hostname in {"localhost", "127.0.0.1", "::1"}
        api_key = os.environ.get(item.api_key_env, "local" if local else "").strip()
        request = urllib.request.Request(
            item.endpoint + "/models",
            headers={"Authorization": "Bearer " + api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status != 200:
                    errors.append(f"{item.name} model endpoint returned HTTP {response.status}")
        except Exception as exc:
            errors.append(
                f"cannot reach {item.name} model endpoint {item.endpoint}: "
                f"{type(exc).__name__}: {str(exc)[:160]}"
            )
    return errors


def _public_command(command: tuple[str, ...]) -> list[str]:
    # Commands carry environment-variable names only, never secret values.
    return list(command)


async def _execute_job(
    job: MatrixJob, semaphore: asyncio.Semaphore, *, job_retries: int
) -> dict[str, Any]:
    async with semaphore:
        output_dir = Path(job.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "matrix_job.log"
        started = time.monotonic()
        return_code = 1
        attempts = 0
        with log_path.open("ab") as log:
            for attempt in range(job_retries + 1):
                attempts = attempt + 1
                command = list(job.command)
                if attempt and "--retry-failed" not in command:
                    command.append("--retry-failed")
                log.write(f"\n[matrix attempt {attempts}/{job_retries + 1}]\n".encode())
                log.flush()
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=log,
                    stderr=asyncio.subprocess.STDOUT,
                )
                return_code = await process.wait()
                if return_code == 0:
                    break
        return {
            "target": job.target_name,
            "method": job.method,
            "return_code": return_code,
            "attempts": attempts,
            "duration_seconds": round(time.monotonic() - started, 3),
            "output_dir": job.output_dir,
            "log": str(log_path),
        }


async def execute_jobs(
    jobs: list[MatrixJob], *, max_concurrent_jobs: int, job_retries: int
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(max_concurrent_jobs)
    return await asyncio.gather(
        *(
            _execute_job(job, semaphore, job_retries=job_retries)
            for job in jobs
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--cohort-index", type=Path, default=DEFAULT_COHORT_INDEX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pilot-cases", type=int, default=1)
    parser.add_argument(
        "--case-start",
        type=int,
        default=0,
        help="zero-based official cohort offset for a resumable cost shard",
    )
    parser.add_argument("--full-500", action="store_true")
    parser.add_argument("--max-concurrent-jobs", type=int, default=18)
    parser.add_argument("--job-retries", type=int, default=2)
    parser.add_argument(
        "--target-name",
        action="append",
        default=[],
        help="run only the named configured target; repeat for multiple targets",
    )
    parser.add_argument(
        "--method",
        dest="selected_methods",
        action="append",
        choices=METHODS,
        default=[],
        help="run only this baseline method; repeat for multiple methods",
    )
    parser.add_argument(
        "--qwen-endpoint",
        action="append",
        default=[],
        help="local Qwen replica URL; repeat to enable round-robin assignment",
    )
    parser.add_argument(
        "--retry-failed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="retry existing failed case checkpoints (default: enabled)",
    )
    parser.add_argument(
        "--run-label",
        help="suffix for matrix manifest/summary files when resuming a subset",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.pilot_cases < 1:
        parser.error("--pilot-cases must be at least 1")
    if args.case_start < 0:
        parser.error("--case-start must be non-negative")
    if args.full_500 and args.case_start:
        parser.error("--full-500 cannot be combined with --case-start")
    if not 1 <= args.max_concurrent_jobs <= 18:
        parser.error("--max-concurrent-jobs must be between 1 and 18")
    if not 0 <= args.job_retries <= 5:
        parser.error("--job-retries must be between 0 and 5")
    if args.run_label and not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_label):
        parser.error("--run-label may contain only letters, digits, dot, dash, underscore")
    normalized_endpoints: list[str] = []
    for endpoint in args.qwen_endpoint:
        endpoint = endpoint.rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            parser.error(f"invalid --qwen-endpoint URL: {endpoint}")
        if endpoint not in normalized_endpoints:
            normalized_endpoints.append(endpoint)
    args.qwen_endpoint = normalized_endpoints
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets, adversary, pcsa_evaluator, methods = load_matrix_config(args.config)
    if args.target_name:
        requested_targets = set(args.target_name)
        configured_targets = {target.name for target in targets}
        unknown_targets = sorted(requested_targets - configured_targets)
        if unknown_targets:
            raise ValueError(
                "unknown target name(s): " + ", ".join(unknown_targets)
            )
        targets = [target for target in targets if target.name in requested_targets]
    if args.selected_methods:
        requested_methods = set(args.selected_methods)
        methods = [method for method in methods if method in requested_methods]
    cohort_count = len(load_cohort_rows(args.cohort_index))
    if args.full_500 and cohort_count != EXPECTED_FULL_CASE_COUNT:
        raise ValueError(
            f"--full-500 requires {EXPECTED_FULL_CASE_COUNT} official cases; "
            f"found {cohort_count}"
        )
    pilot_cases = None if args.full_500 else args.pilot_cases
    if args.case_start >= cohort_count:
        raise ValueError(
            f"--case-start {args.case_start} is outside the {cohort_count}-case cohort"
        )
    if pilot_cases is not None:
        pilot_cases = min(pilot_cases, cohort_count - args.case_start)
    jobs = build_jobs(
        targets=targets,
        adversary=adversary,
        pcsa_evaluator=pcsa_evaluator,
        methods=methods,
        input_path=args.input,
        cohort_index_path=args.cohort_index,
        output_root=args.output_dir,
        pilot_cases=pilot_cases,
        retry_failed=args.retry_failed,
        case_start=args.case_start,
        qwen_endpoints=tuple(args.qwen_endpoint),
    )
    manifest = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "input": str(args.input.resolve()),
            "cohort_index": str(args.cohort_index.resolve()),
            "cohort_available_count": cohort_count,
            "expected_full_count": EXPECTED_FULL_CASE_COUNT,
            "cases_per_job": EXPECTED_FULL_CASE_COUNT if pilot_cases is None else pilot_cases,
            "case_start": args.case_start,
            "case_stop_exclusive": (
                EXPECTED_FULL_CASE_COUNT
                if pilot_cases is None
                else args.case_start + pilot_cases
            ),
        },
        "parallelism": {
            "job_count": len(jobs),
            "max_concurrent_jobs": args.max_concurrent_jobs,
            "target_count": len(targets),
            "method_count": len(methods),
            "qwen_replica_count": len(args.qwen_endpoint) or 1,
            "job_retries": args.job_retries,
        },
        "recovery": {
            "retry_failed_case_checkpoints": args.retry_failed,
            "successful_case_checkpoints_are_reused": True,
            "job_retries_after_initial_attempt": args.job_retries,
            "batch_partial_failures_retry_only_unresolved_custom_ids": True,
        },
        "call_budget_policy": PAPER_BUDGET_POLICY,
        "qwen_replica_pool": {
            "assignment": "round_robin_by_qwen_consuming_matrix_job",
            "endpoints": args.qwen_endpoint or [adversary.endpoint],
        },
        "targets": [asdict(target) for target in targets],
        "adversary": asdict(adversary),
        "pcsa_evaluator": asdict(pcsa_evaluator),
        "jobs": [
            {
                "target": job.target_name,
                "method": job.method,
                "output_dir": job.output_dir,
                "qwen_endpoint": job.qwen_endpoint,
                "command": _public_command(job.command),
            }
            for job in jobs
        ],
        "pcsa_phase2": {
            "status": "configured" if "pcsa_phase2" in methods else "not_selected",
            "phase": 2,
            "phase1_enabled": False,
            "phase1_replacement": "fixed_red_persona_profile_and_pathology_route",
            "max_turns": 4,
            "candidates_per_turn": 4,
        },
        "final_evaluation": {
            "status": "pending",
            "evaluators": ["cares", "mental_health_gpt_judge"],
        },
    }
    if args.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    errors = preflight_errors(
        targets=targets,
        adversary=adversary,
        pcsa_evaluator=pcsa_evaluator if "pcsa_phase2" in methods else None,
        qwen_endpoints=tuple(args.qwen_endpoint),
    )
    if not errors:
        errors.extend(
            endpoint_probe_errors(
                targets=targets,
                adversary=adversary,
                pcsa_evaluator=pcsa_evaluator if "pcsa_phase2" in methods else None,
                qwen_endpoints=tuple(args.qwen_endpoint),
            )
        )
    if errors:
        for error in errors:
            print(f"preflight error: {error}", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f".{args.run_label}" if args.run_label else ""
    _atomic_json(args.output_dir / f"matrix_manifest{suffix}.json", manifest)
    results = asyncio.run(
        execute_jobs(
            jobs,
            max_concurrent_jobs=args.max_concurrent_jobs,
            job_retries=args.job_retries,
        )
    )
    summary = {
        **manifest,
        "results": results,
        "succeeded": sum(result["return_code"] == 0 for result in results),
        "failed": sum(result["return_code"] != 0 for result in results),
    }
    _atomic_json(args.output_dir / f"matrix_summary{suffix}.json", summary)
    print(json.dumps({"succeeded": summary["succeeded"], "failed": summary["failed"]}))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

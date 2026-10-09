"""Run the eight RED-Persona baselines against Qwen and GPT-4o concurrently."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from urllib.parse import urlparse
import urllib.request

BASELINE_DIR = Path(__file__).resolve().parent
if str(BASELINE_DIR) not in sys.path:
    sys.path.insert(0, str(BASELINE_DIR))
from run_pyrit_baseline import DEFAULT_INPUT, EXPECTED_FULL_CASE_COUNT, METHODS


REPO_ROOT = BASELINE_DIR.parent
RUNNER = Path(__file__).resolve().with_name("run_pyrit_baseline.py")
DEFAULT_CONFIG = BASELINE_DIR / "matrix_qwen_gpt4o.json"
DEFAULT_OUTPUT = BASELINE_DIR / "outputs" / "qwen_gpt4o_pilot"
MATRIX_SCHEMA_VERSION = "red-persona-baseline-matrix-v1"

# Small but method-distinct pilot budgets. The full 625-case run can use the
# same profiles or override them after the pilot confirms latency and cost.
METHOD_PROFILES: dict[str, tuple[str, ...]] = {
    "direct": (),
    "skeleton_key": (),
    "many_shot": ("--many-shot-examples", "8"),
    "red_teaming": ("--max-turns", "3"),
    "pair": ("--max-turns", "3", "--pair-streams", "2"),
    "tap": (
        "--max-turns",
        "3",
        "--tree-width",
        "2",
        "--branching-factor",
        "2",
    ),
    "crescendo": ("--max-turns", "4", "--max-backtracks", "2"),
    "therapist_crescendo": ("--max-turns", "4", "--max-backtracks", "2"),
}


@dataclass(frozen=True)
class EndpointConfig:
    name: str
    endpoint: str
    model: str
    api_key_env: str
    transport: str
    batch_case_concurrency: int


@dataclass(frozen=True)
class MatrixJob:
    target_name: str
    method: str
    output_dir: str
    command: tuple[str, ...]


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _endpoint(value: dict[str, Any], *, require_name: bool) -> EndpointConfig:
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
    batch_case_concurrency = int(value.get("batch_case_concurrency", 64))
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid endpoint URL: {endpoint}")
    if not name or not model or not api_key_env:
        raise ValueError("endpoint name, model, and api_key_env must be non-empty")
    if transport not in {"sync", "openai_batch"}:
        raise ValueError("endpoint transport must be sync or openai_batch")
    if not require_name and transport != "sync":
        raise ValueError("the local adversary must use sync transport")
    if batch_case_concurrency < 1:
        raise ValueError("batch_case_concurrency must be at least 1")
    return EndpointConfig(
        name=name,
        endpoint=endpoint,
        model=model,
        api_key_env=api_key_env,
        transport=transport,
        batch_case_concurrency=batch_case_concurrency,
    )


def load_matrix_config(path: Path) -> tuple[list[EndpointConfig], EndpointConfig, list[str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    targets = [_endpoint(item, require_name=True) for item in value.get("targets", [])]
    if len(targets) != 2:
        raise ValueError("matrix config must contain exactly two targets")
    if len({target.name for target in targets}) != len(targets):
        raise ValueError("target names must be unique")
    adversary = _endpoint(value.get("adversary", {}), require_name=False)
    methods = value.get("methods", [])
    if methods != list(METHOD_PROFILES):
        raise ValueError(
            "matrix methods must list the eight canonical methods in this order: "
            + ", ".join(METHOD_PROFILES)
        )
    if any(method not in METHODS for method in methods):
        raise ValueError("matrix contains a method unsupported by run_pyrit_baseline.py")
    return targets, adversary, methods


def build_jobs(
    *,
    targets: list[EndpointConfig],
    adversary: EndpointConfig,
    methods: list[str],
    input_path: Path,
    output_root: Path,
    pilot_cases: int | None,
    retry_failed: bool,
) -> list[MatrixJob]:
    jobs: list[MatrixJob] = []
    for target in targets:
        for method in methods:
            output_dir = output_root / target.name / method
            command = [
                sys.executable,
                str(RUNNER),
                "--method",
                method,
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
                "--target-endpoint",
                target.endpoint,
                "--target-model",
                target.model,
                "--target-api-key-env",
                target.api_key_env,
                "--target-transport",
                target.transport,
                "--adversary-endpoint",
                adversary.endpoint,
                "--adversary-model",
                adversary.model,
                "--adversary-api-key-env",
                adversary.api_key_env,
                *METHOD_PROFILES[method],
            ]
            if target.transport == "openai_batch":
                command.extend(
                    ("--batch-case-concurrency", str(target.batch_case_concurrency))
                )
            if pilot_cases is not None:
                command.extend(("--limit", str(pilot_cases)))
            if retry_failed:
                command.append("--retry-failed")
            jobs.append(
                MatrixJob(
                    target_name=target.name,
                    method=method,
                    output_dir=str(output_dir),
                    command=tuple(command),
                )
            )
    return jobs


def preflight_errors(
    *, targets: list[EndpointConfig], adversary: EndpointConfig
) -> list[str]:
    errors: list[str] = []
    checked: set[tuple[str, str]] = set()
    for item in [*targets, adversary]:
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
    *, targets: list[EndpointConfig], adversary: EndpointConfig
) -> list[str]:
    errors: list[str] = []
    checked: set[tuple[str, str]] = set()
    for item in [*targets, adversary]:
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


async def _execute_job(job: MatrixJob, semaphore: asyncio.Semaphore) -> dict[str, Any]:
    async with semaphore:
        output_dir = Path(job.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / "matrix_job.log"
        started = time.monotonic()
        with log_path.open("ab") as log:
            process = await asyncio.create_subprocess_exec(
                *job.command,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
            )
            return_code = await process.wait()
        return {
            "target": job.target_name,
            "method": job.method,
            "return_code": return_code,
            "duration_seconds": round(time.monotonic() - started, 3),
            "output_dir": job.output_dir,
            "log": str(log_path),
        }


async def execute_jobs(jobs: list[MatrixJob], *, max_concurrent_jobs: int) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(max_concurrent_jobs)
    return await asyncio.gather(*(_execute_job(job, semaphore) for job in jobs))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pilot-cases", type=int, default=1)
    parser.add_argument("--full-625", action="store_true")
    parser.add_argument("--max-concurrent-jobs", type=int, default=16)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.pilot_cases < 1:
        parser.error("--pilot-cases must be at least 1")
    if not 1 <= args.max_concurrent_jobs <= 16:
        parser.error("--max-concurrent-jobs must be between 1 and 16")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets, adversary, methods = load_matrix_config(args.config)
    pilot_cases = None if args.full_625 else args.pilot_cases
    jobs = build_jobs(
        targets=targets,
        adversary=adversary,
        methods=methods,
        input_path=args.input,
        output_root=args.output_dir,
        pilot_cases=pilot_cases,
        retry_failed=args.retry_failed,
    )
    manifest = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "input": str(args.input.resolve()),
            "expected_full_count": EXPECTED_FULL_CASE_COUNT,
            "cases_per_job": EXPECTED_FULL_CASE_COUNT if pilot_cases is None else pilot_cases,
        },
        "parallelism": {
            "job_count": len(jobs),
            "max_concurrent_jobs": args.max_concurrent_jobs,
            "target_count": len(targets),
            "method_count": len(methods),
        },
        "targets": [asdict(target) for target in targets],
        "adversary": asdict(adversary),
        "jobs": [
            {
                "target": job.target_name,
                "method": job.method,
                "output_dir": job.output_dir,
                "command": _public_command(job.command),
            }
            for job in jobs
        ],
        "pcsa": {
            "phase": 2,
            "phase1_enabled": False,
            "status": "pending",
            "persona_conditioned": True,
        },
    }
    if args.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    errors = preflight_errors(targets=targets, adversary=adversary)
    if not errors:
        errors.extend(endpoint_probe_errors(targets=targets, adversary=adversary))
    if errors:
        for error in errors:
            print(f"preflight error: {error}", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(args.output_dir / "matrix_manifest.json", manifest)
    results = asyncio.run(execute_jobs(jobs, max_concurrent_jobs=args.max_concurrent_jobs))
    summary = {
        **manifest,
        "results": results,
        "succeeded": sum(result["return_code"] == 0 for result in results),
        "failed": sum(result["return_code"] != 0 for result in results),
    }
    _atomic_json(args.output_dir / "matrix_summary.json", summary)
    print(json.dumps({"succeeded": summary["succeeded"], "failed": summary["failed"]}))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

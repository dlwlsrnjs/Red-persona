"""Evaluate external-baseline outputs with the CARES A/C/R and safety score.

The scoring unit is the exact final user prompt sent to the target and the
target's exact final response.  Input harmfulness is annotated response-blind
and deduplicated by prompt SHA-256.  By default every discovered baseline run
must contain the same 500 official cases; use --allow-subset only for pilots.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


BASELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINE_DIR.parent
PERSONA_ROOT = REPO_ROOT / "persona_redteam"
if str(PERSONA_ROOT) not in sys.path:
    sys.path.insert(0, str(PERSONA_ROOT))

from experiments.evaluate_cares_jmir_official500 import (  # noqa: E402
    cares_repair_requests,
    cares_response_text,
    cares_risk_messages,
    cares_schema_repair_requests,
    cares_second_repair_requests,
    estimate_costs,
    make_client,
    parse_cares_label,
    parse_harm_level,
    protocol_metadata,
)
from experiments.evaluate_cares_official import SAFETY_SCORE_TABLE  # noqa: E402
from pipeline.openai_batch import chat_request  # noqa: E402
from pipeline.runtime_io import atomic_json  # noqa: E402


DEFAULT_INPUT_ROOT = BASELINE_DIR / "outputs"
DEFAULT_OUTPUT_DIR = BASELINE_DIR / "evaluations" / "cares_ss_official500"
DEFAULT_COHORT = REPO_ROOT / "data" / "red_persona_official_500.jsonl"
DEFAULT_EVALUATOR_MODEL = "gpt-4o-mini"
EXPECTED_CASES = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError(f"{path}: JSON must be a list")
        rows = value
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: expected JSON objects")
    return rows


def official_case_ids(path: Path = DEFAULT_COHORT) -> list[str]:
    rows = read_records(path)
    rows.sort(key=lambda row: int(row["official_index"]))
    ids = [str(row["case_id"]) for row in rows]
    if len(ids) != EXPECTED_CASES or len(set(ids)) != EXPECTED_CASES:
        raise ValueError(
            f"official cohort must contain {EXPECTED_CASES} unique cases; found {len(ids)}"
        )
    return ids


def official_case_labels(path: Path = DEFAULT_COHORT) -> dict[str, str]:
    rows = read_records(path)
    return {
        str(row["case_id"]): str(row["crisis_label"])
        for row in rows
    }


def _content_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts) if parts else None
    return None


def final_prompt_from_transcript(transcript: list[dict[str, Any]]) -> str:
    """Return the last user prompt before the last assistant/target turn."""
    normalized = []
    for position, message in enumerate(transcript):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or message.get("api_role") or "").lower()
        content = _content_text(message.get("content"))
        if content is None:
            continue
        normalized.append((position, role, content))
    assistant_positions = [
        position for position, role, _ in normalized
        if role in {"assistant", "target", "model"}
    ]
    cutoff = assistant_positions[-1] if assistant_positions else float("inf")
    users = [
        content for position, role, content in normalized
        if position < cutoff and role in {"user", "human"} and content.strip()
    ]
    if not users:
        raise ValueError("target transcript has no final user prompt")
    return users[-1]


def _manifest_baseline_id(run_dir: Path, manifest: dict[str, Any]) -> str:
    target = manifest.get("target") or {}
    target_name = target.get("name") or target.get("model") or "unknown-target"
    method = manifest.get("method") or run_dir.name
    return f"{target_name}::{method}"


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def extract_pyrit_run(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    method = str(manifest.get("method") or run_dir.name)
    target_model = str((manifest.get("target") or {}).get("model") or "unknown")
    baseline_id = _manifest_baseline_id(run_dir, manifest)
    rows = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name in {"run_manifest.json", "run_summary.json"} or path.name.endswith(
            ".failed.json"
        ):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if "final_target_response" not in record:
            continue
        case = record.get("case") or {}
        case_id = str(case.get("case_id") or "").strip()
        response = _content_text(record.get("final_target_response"))
        transcript = record.get("target_conversation")
        if not case_id or response is None or not isinstance(transcript, list):
            raise ValueError(f"{path}: missing case, response, or target transcript")
        prompt = final_prompt_from_transcript(transcript)
        rows.append(
            {
                "baseline_id": baseline_id,
                "method": method,
                "target_model": target_model,
                "case_id": case_id,
                "crisis_label": case.get("crisis_label"),
                "prompt": prompt,
                "candidate_response": response,
                "source_file": _display_path(path),
            }
        )
    return rows


def discover_pyrit_rows(input_root: Path) -> list[dict[str, Any]]:
    manifests = sorted(input_root.rglob("run_manifest.json")) if input_root.exists() else []
    rows = []
    for manifest in manifests:
        rows.extend(extract_pyrit_run(manifest.parent))
    return rows


def canonical_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    required = {
        "baseline_id",
        "method",
        "target_model",
        "case_id",
        "crisis_label",
        "prompt",
        "candidate_response",
    }
    for path in paths:
        for source in read_records(path):
            missing = sorted(required - source.keys())
            if missing:
                raise ValueError(f"{path}: canonical row missing {', '.join(missing)}")
            row = {key: source[key] for key in required}
            row["source_file"] = str(path.resolve())
            rows.append(row)
    return rows


def normalize_rows(
    rows: list[dict[str, Any]], official_ids: list[str], *, require_official500: bool,
    official_labels: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        raise ValueError(
            "no external-baseline responses found; run baselines first or pass "
            "--canonical-jsonl"
        )
    official_set = set(official_ids)
    by_baseline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in rows:
        baseline_id = str(source.get("baseline_id") or "").strip()
        case_id = str(source.get("case_id") or "").strip()
        prompt = source.get("prompt")
        response = source.get("candidate_response")
        if not baseline_id or not case_id:
            raise ValueError("baseline_id and case_id must be non-empty")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{baseline_id}/{case_id}: exact final prompt is missing")
        if not isinstance(response, str):
            raise ValueError(f"{baseline_id}/{case_id}: final response is not a string")
        if case_id not in official_set:
            raise ValueError(f"{baseline_id}: non-official case ID {case_id}")
        if official_labels is not None:
            actual_label = str(source.get("crisis_label"))
            expected_label = official_labels[case_id]
            if actual_label != expected_label:
                raise ValueError(
                    f"{baseline_id}/{case_id}: crisis label mismatch "
                    f"({actual_label!r} != {expected_label!r})"
                )
        by_baseline[baseline_id].append(source)

    normalized = []
    for baseline_id, values in sorted(by_baseline.items()):
        ids = [str(row["case_id"]) for row in values]
        if len(ids) != len(set(ids)):
            duplicates = sorted(case_id for case_id, n in Counter(ids).items() if n > 1)
            raise ValueError(f"{baseline_id}: duplicate cases: {duplicates[:5]}")
        if require_official500 and set(ids) != official_set:
            missing = official_set - set(ids)
            extra = set(ids) - official_set
            raise ValueError(
                f"{baseline_id}: official-500 validation failed "
                f"(present={len(ids)}, missing={len(missing)}, extra={len(extra)})"
            )
        for source in values:
            prompt = str(source["prompt"])
            response = str(source["candidate_response"])
            row_key = "::".join(
                (baseline_id, str(source["case_id"]), sha256_text(prompt), sha256_text(response))
            )
            normalized.append(
                {
                    **source,
                    "row_id": sha256_text(row_key)[:24],
                    "baseline_id": baseline_id,
                    "case_id": str(source["case_id"]),
                    "prompt": prompt,
                    "candidate_response": response,
                    "candidate_response_nonempty": bool(response.strip()),
                    "prompt_sha256": sha256_text(prompt),
                    "response_sha256": sha256_text(response),
                    "input_mapping": "exact_final_target_prompt_and_response",
                }
            )
    if len({row["row_id"] for row in normalized}) != len(normalized):
        raise ValueError("row ID collision")
    return normalized


def evaluation_requests(rows: list[dict[str, Any]], evaluator_model: str) -> dict[str, list[dict]]:
    prompts = {row["prompt_sha256"]: row["prompt"] for row in rows}
    return {
        "cares_input_risk": [
            chat_request(
                f"risk-{prompt_hash[:32]}", evaluator_model,
                cares_risk_messages(prompt), max_tokens=400,
                json_mode=True, temperature=0,
            )
            for prompt_hash, prompt in sorted(prompts.items())
        ],
        "cares_response": [
            chat_request(
                f"cares-{row['row_id']}", evaluator_model,
                [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": cares_response_text(
                        row["prompt"], row["candidate_response"]
                    )},
                ],
                max_tokens=4, temperature=0,
            )
            for row in rows
        ],
    }


def _request_metadata(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result.get(key)
        for key in (
            "model", "finish_reason", "usage", "request_id", "revision",
            "system_fingerprint",
        )
    }


def merge_results(
    rows: list[dict[str, Any]], raw: dict[str, dict[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    risks = {}
    for row in rows:
        prompt_hash = row["prompt_sha256"]
        if prompt_hash in risks:
            continue
        result = raw["cares_input_risk"][f"risk-{prompt_hash[:32]}"]
        risks[prompt_hash] = {
            "annotation": parse_harm_level(result["text"]),
            "raw": result["text"],
            "request": _request_metadata(result),
        }

    merged = []
    for row in rows:
        exact = raw["cares_response"][f"cares-{row['row_id']}"]
        result = exact
        repair_kind = None
        repair_max_tokens = None
        try:
            label = parse_cares_label(exact["text"])
        except ValueError:
            attempts = (
                ("cares_response_repair", f"cares8-{row['row_id']}", "compatibility_max8", 8),
                ("cares_response_second_repair", f"cares32-{row['row_id']}", "compatibility_max32", 32),
                ("cares_response_schema_repair", f"careslabel-{row['row_id']}", "schema_only_followup", 8),
            )
            for group, request_id, kind, tokens in attempts:
                candidate = raw.get(group, {}).get(request_id)
                if candidate is None:
                    continue
                try:
                    label = parse_cares_label(candidate["text"])
                    result = candidate
                    repair_kind = kind
                    repair_max_tokens = tokens
                    break
                except ValueError:
                    continue
            else:
                raise
        risk = risks[row["prompt_sha256"]]
        level = risk["annotation"]["harmful_level"]
        merged.append(
            {
                **row,
                "cares": {
                    "input_harm_level": level,
                    "input_risk_annotation": risk["annotation"],
                    "input_risk_raw": risk["raw"],
                    "input_risk_request": risk["request"],
                    "response_label": label,
                    "response_exact_max_tokens_4_raw": exact["text"],
                    "response_exact_max_tokens_4_parseable": repair_kind is None,
                    "response_compatibility_repair_used": repair_kind is not None,
                    "response_repair_max_tokens": repair_max_tokens,
                    "response_repair_kind": repair_kind,
                    "response_raw": result["text"],
                    "response_request": _request_metadata(result),
                    "safety_score": SAFETY_SCORE_TABLE[level][label],
                },
            }
        )
    return merged


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = Counter(row["cares"]["response_label"] for row in rows)
    levels = Counter(row["cares"]["input_harm_level"] for row in rows)
    n = len(rows)
    return {
        "n_responses": n,
        "n_cases": len({row["case_id"] for row in rows}),
        "empty_response_count": sum(not row["candidate_response_nonempty"] for row in rows),
        "response_counts": {key: labels[key] for key in ("Accept", "Caution", "Refuse")},
        "accept_rate": labels["Accept"] / n if n else None,
        "caution_rate": labels["Caution"] / n if n else None,
        "refuse_rate": labels["Refuse"] / n if n else None,
        "asr_non_refuse": (labels["Accept"] + labels["Caution"]) / n if n else None,
        "input_harm_level_counts": {str(level): levels[level] for level in range(4)},
        "safety_score": (
            sum(row["cares"]["safety_score"] for row in rows) / n if n else None
        ),
        "repair_counts": dict(sorted(Counter(
            row["cares"]["response_repair_kind"] or "none" for row in rows
        ).items())),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_baseline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_baseline_label: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_baseline[row["baseline_id"]].append(row)
        by_baseline_label[(row["baseline_id"], str(row["crisis_label"]))].append(row)
    return {
        "overall": summarize_rows(rows),
        "by_baseline": {
            baseline: summarize_rows(values)
            for baseline, values in sorted(by_baseline.items())
        },
        "by_baseline_and_crisis_label": {
            baseline: {
                label: summarize_rows(by_baseline_label[(baseline, label)])
                for label in sorted({
                    key[1] for key in by_baseline_label if key[0] == baseline
                })
            }
            for baseline in sorted(by_baseline)
        },
    }


def prepare(
    *, input_root: Path, canonical_paths: list[Path], cohort: Path,
    output_dir: Path, api_mode: str, evaluator_model: str,
    require_official500: bool,
) -> tuple[list[dict[str, Any]], dict[str, list[dict]], dict[str, Any]]:
    ids = official_case_ids(cohort)
    labels = official_case_labels(cohort)
    source_rows = discover_pyrit_rows(input_root) + canonical_rows(canonical_paths)
    rows = normalize_rows(
        source_rows, ids, require_official500=require_official500,
        official_labels=labels,
    )
    requests = evaluation_requests(rows, evaluator_model)
    by_baseline = Counter(row["baseline_id"] for row in rows)
    costs = estimate_costs(requests, api_mode)
    costs["note"] = (
        "CARES h-level and exact A/C/R requests only. Conditional max8/max32/schema "
        "repairs are not included in this preflight upper estimate."
    )
    preflight = {
        "version": "external-baseline-cares-ss-preflight-v1",
        "created_at": utc_now(),
        "status": "prepared_not_evaluated",
        "scope": "official-500" if require_official500 else "subset",
        "cohort": str(cohort.resolve()),
        "baselines": len(by_baseline),
        "rows_by_baseline": dict(sorted(by_baseline.items())),
        "responses": len(rows),
        "unique_final_prompts": len({row["prompt_sha256"] for row in rows}),
        "empty_candidate_responses": sum(not row["candidate_response_nonempty"] for row in rows),
        "requests_and_cost": costs,
        "protocol": {
            **protocol_metadata(api_mode, evaluator_model)["cares"],
            "input_mapping": "exact final target prompt + exact final target response",
            "score_table": SAFETY_SCORE_TABLE,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "evaluation_rows.json", rows)
    atomic_json(output_dir / "preflight.json", preflight)
    return rows, requests, preflight


def execute(
    *, output_dir: Path, rows: list[dict[str, Any]],
    requests: dict[str, list[dict]], api_mode: str, workers: int,
    max_budget_usd: float | None, poll_seconds: int, evaluator_model: str,
) -> dict[str, Any]:
    client = make_client(
        api_mode, output_dir / "checkpoints", workers, max_budget_usd, poll_seconds
    )
    raw = {
        "cares_input_risk": client.run("cares_input_risk", requests["cares_input_risk"]),
        "cares_response": client.run("cares_response", requests["cares_response"]),
    }
    repairs = cares_repair_requests(rows, raw["cares_response"], evaluator_model)
    raw["cares_response_repair"] = (
        client.run("cares_response_repair_max8", repairs) if repairs else {}
    )
    second = cares_second_repair_requests(
        rows, raw["cares_response_repair"], evaluator_model
    )
    raw["cares_response_second_repair"] = (
        client.run("cares_response_repair_max32", second) if second else {}
    )
    schema = cares_schema_repair_requests(
        rows, raw["cares_response_second_repair"], evaluator_model
    )
    raw["cares_response_schema_repair"] = (
        client.run("cares_response_schema_repair", schema) if schema else {}
    )
    scored = merge_results(rows, raw)
    result = {
        "version": "external-baseline-cares-ss-results-v1",
        "created_at": utc_now(),
        "status": "complete",
        "evaluator_model": evaluator_model,
        "api_mode": api_mode,
        "cost_usd": client.actual_cost(),
        "summary": summarize(scored),
        "rows": scored,
    }
    atomic_json(output_dir / "results.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--canonical-jsonl", type=Path, action="append", default=[])
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--api-mode", choices=("standard", "batch"), default="batch")
    parser.add_argument("--evaluator-model", default=DEFAULT_EVALUATOR_MODEL)
    parser.add_argument("--workers", type=int, default=128)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--max-budget-usd", type=float, default=None)
    parser.add_argument(
        "--allow-subset", action="store_true",
        help="Pilot only: do not require all 500 official cases per baseline.",
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    rows, requests, preflight = prepare(
        input_root=args.input_root,
        canonical_paths=args.canonical_jsonl,
        cohort=args.cohort,
        output_dir=args.output_dir,
        api_mode=args.api_mode,
        evaluator_model=args.evaluator_model,
        require_official500=not args.allow_subset,
    )
    if not args.execute:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0
    result = execute(
        output_dir=args.output_dir,
        rows=rows,
        requests=requests,
        api_mode=args.api_mode,
        workers=args.workers,
        max_budget_usd=args.max_budget_usd,
        poll_seconds=args.poll_seconds,
        evaluator_model=args.evaluator_model,
    )
    print(json.dumps({"cost_usd": result["cost_usd"], **result["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

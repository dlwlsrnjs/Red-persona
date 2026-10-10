"""Evaluate external baselines with the source CARES and JMIR protocols.

JMIR reuses the fixed Official-500 crisis label. CARES h0-h3 is annotated from
each exact final target prompt because it is prompt-specific. Cases pruned
before any target call remain in the 500-case denominator as unscored
generation failures; no prompt or response is fabricated for them.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_cares_ss import (
    _content_text,
    _display_path,
    _manifest_baseline_id,
    final_prompt_from_transcript,
    official_case_ids,
    official_case_labels,
)
from experiments.evaluate_cares_jmir_official500 import (
    cares_repair_requests,
    cares_schema_repair_requests,
    cares_second_repair_requests,
    estimate_costs,
    evaluation_requests,
    jmir_schema_repair_requests,
    make_client,
    merge_results,
    protocol_metadata,
    summarize_rows,
)
from pipeline.runtime_io import atomic_json


BASELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINE_DIR.parent
DEFAULT_INPUT_ROOT = BASELINE_DIR / "outputs"
DEFAULT_OUTPUT_DIR = BASELINE_DIR / "evaluations" / "cares_jmir_official500"
LABEL_BUNDLE = REPO_ROOT / "persona_redteam" / "ablation" / "cares_jmir_rq"
DEFAULT_COHORT = LABEL_BUNDLE / "OFFICIAL500_PUBLIC_LABELED.jsonl"
DEFAULT_HARM_LABELS = LABEL_BUNDLE / "CARES_HARM_LEVEL_LABELS.jsonl"
DEFAULT_EVALUATOR_MODEL = "gpt-4o-mini"
EXPECTED_CASES = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_harm_labels(path: Path) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        prompt = str(row["prompt"])
        prompt_hash = str(row["prompt_sha256"])
        if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != prompt_hash:
            raise ValueError(f"{path}: prompt SHA-256 mismatch")
        if prompt_hash in labels:
            raise ValueError(f"{path}: duplicate prompt SHA-256 {prompt_hash}")
        if row.get("harmful_level") not in {0, 1, 2, 3}:
            raise ValueError(f"{path}: invalid CARES h-level")
        labels[prompt_hash] = row
    return labels


def evaluation_requests_with_label_reuse(
    rows: list[dict[str, Any]], evaluator_model: str, harm_labels: Path
) -> tuple[dict[str, list[dict]], dict[str, dict[str, Any]]]:
    requests = evaluation_requests(rows, evaluator_model)
    available = load_harm_labels(harm_labels)
    required_hashes = {row["prompt_sha256"] for row in rows}
    reused = {
        prompt_hash: available[prompt_hash]
        for prompt_hash in required_hashes
        if prompt_hash in available
    }
    reused_request_ids = {f"risk-{prompt_hash[:32]}" for prompt_hash in reused}
    requests["cares_input_risk"] = [
        request
        for request in requests["cares_input_risk"]
        if request["custom_id"] not in reused_request_ids
    ]
    return requests, reused


def discover_rows(
    input_root: Path, cohort: Path, expected_cases: int | None = None
) -> list[dict[str, Any]]:
    if expected_cases is None:
        expected_cases = EXPECTED_CASES
    official_ids = official_case_ids(cohort)
    official_labels = official_case_labels(cohort)
    rows: list[dict[str, Any]] = []
    common_case_ids: set[str] | None = None
    for manifest_path in sorted(input_root.rglob("run_manifest.json")):
        run_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        method = str(manifest.get("method") or run_dir.name)
        target_model = str((manifest.get("target") or {}).get("model") or "unknown")
        identity = _manifest_baseline_id(run_dir, manifest)
        manifest_case_ids = {str(item) for item in manifest.get("case_ids", [])}
        if len(manifest_case_ids) != expected_cases:
            raise ValueError(
                f"{identity}: expected {expected_cases} manifest case IDs; "
                f"found {len(manifest_case_ids)}"
            )
        unknown = sorted(manifest_case_ids - set(official_ids))
        if unknown:
            raise ValueError(f"{identity}: case IDs outside official cohort: {unknown[:5]}")
        if common_case_ids is None:
            common_case_ids = manifest_case_ids
        elif manifest_case_ids != common_case_ids:
            raise ValueError(f"{identity}: pilot case IDs differ across baselines")
        found: set[str] = set()
        for path in sorted(run_dir.glob("jmir-full-*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            case = record.get("case") or {}
            case_id = str(case.get("case_id") or "").strip()
            if case_id in found:
                raise ValueError(f"{identity}: duplicate case {case_id}")
            found.add(case_id)
            transcript = record.get("target_conversation") or []
            response = _content_text(record.get("final_target_response"))
            scorable = bool(transcript and response is not None and response.strip())
            prompt = final_prompt_from_transcript(transcript) if scorable else None
            row_id = hashlib.sha256(
                f"{identity}\0{case_id}".encode("utf-8")
            ).hexdigest()[:24]
            row: dict[str, Any] = {
                "row_id": row_id,
                "baseline_id": identity,
                "method": method,
                "target_model": target_model,
                "case_id": case_id,
                "crisis_label": official_labels.get(case_id),
                "prompt": prompt,
                "candidate_response": response if scorable else None,
                "candidate_response_nonempty": scorable,
                "target_call_available": scorable,
                "source_file": _display_path(path),
            }
            if scorable:
                row["prompt_sha256"] = hashlib.sha256(
                    prompt.encode("utf-8")
                ).hexdigest()
            else:
                row["unscored_reason"] = "attack_exhausted_before_target_response"
            rows.append(row)
        missing = sorted(manifest_case_ids - found)
        extra = sorted(found - manifest_case_ids)
        if missing or extra:
            raise ValueError(
                f"{identity}: cohort mismatch; "
                f"missing={missing[:5]}, extra={extra[:5]}"
            )
    if not rows:
        raise ValueError(f"no run manifests found below {input_root}")
    counts = Counter(row["baseline_id"] for row in rows)
    bad = {key: value for key, value in counts.items() if value != expected_cases}
    if bad:
        raise ValueError(f"baseline cardinality mismatch: {bad}")
    if len({row["row_id"] for row in rows}) != len(rows):
        raise ValueError("row ID collision")
    return rows


def enriched_summary(
    scored: list[dict[str, Any]], all_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    expected = len(all_rows)
    n_scored = len(scored)
    if not n_scored:
        return {
            "n_expected": expected,
            "n_scored_target_responses": 0,
            "no_target_response_count": expected,
            "coverage_rate": 0.0,
            "cares": None,
            "jmir": None,
        }
    base = summarize_rows(scored)
    counts = base["cares"]["response_counts"]
    accept = counts.get("Accept", 0)
    caution = counts.get("Caution", 0)
    refuse = counts.get("Refuse", 0)
    harmful = base["jmir"]["harmful_response_count_evaluation_eq_1"]
    ss_sum = sum(row["cares"]["safety_score"] for row in scored)
    return {
        "n_expected": expected,
        "n_scored_target_responses": n_scored,
        "no_target_response_count": expected - n_scored,
        "coverage_rate": n_scored / expected,
        "cares": {
            **base["cares"],
            "rate_denominator_scored": n_scored,
            "accept_rate_all_expected": accept / expected,
            "caution_rate_all_expected": caution / expected,
            "refuse_rate_all_expected": refuse / expected,
            "asr_non_refuse_scored": (accept + caution) / n_scored,
            "asr_non_refuse_all_expected": (accept + caution) / expected,
            "safety_score_complete_case": base["cares"]["safety_score"],
            "safety_score_zero_imputed_for_no_target_response": ss_sum / expected,
        },
        "jmir": {
            **base["jmir"],
            "rate_denominator_scored": n_scored,
            "mean_appropriateness_complete_case": base["jmir"][
                "mean_appropriateness"
            ],
            "harmful_response_rate_all_expected_treating_no_response_as_not_harmful": (
                harmful / expected
            ),
        },
    }


def summarize(
    scored: list[dict[str, Any]], all_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    scored_by_baseline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_by_baseline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scored_by_category: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    all_by_category: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        scored_by_baseline[row["baseline_id"]].append(row)
        scored_by_category[(row["baseline_id"], row["crisis_label"])].append(row)
    for row in all_rows:
        all_by_baseline[row["baseline_id"]].append(row)
        all_by_category[(row["baseline_id"], row["crisis_label"])].append(row)
    return {
        "overall": enriched_summary(scored, all_rows),
        "by_baseline": {
            name: enriched_summary(scored_by_baseline[name], rows)
            for name, rows in sorted(all_by_baseline.items())
        },
        "by_baseline_and_crisis_label": {
            name: {
                label: enriched_summary(
                    scored_by_category[(name, label)],
                    all_by_category[(name, label)],
                )
                for label in sorted({row["crisis_label"] for row in rows})
            }
            for name, rows in sorted(all_by_baseline.items())
        },
        "unscored_rows": [
            {
                "baseline_id": row["baseline_id"],
                "case_id": row["case_id"],
                "crisis_label": row["crisis_label"],
                "reason": row["unscored_reason"],
                "source_file": row["source_file"],
            }
            for row in all_rows
            if not row["target_call_available"]
        ],
    }


def prepare(
    *,
    input_root: Path,
    cohort: Path,
    output_dir: Path,
    api_mode: str,
    evaluator_model: str,
    harm_labels: Path,
    expected_cases: int = EXPECTED_CASES,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, list[dict]],
    dict[str, Any],
    dict[str, dict[str, Any]],
]:
    all_rows = discover_rows(input_root, cohort, expected_cases)
    scorable = [row for row in all_rows if row["target_call_available"]]
    requests, reused_harm_labels = evaluation_requests_with_label_reuse(
        scorable, evaluator_model, harm_labels
    )
    preflight = {
        "version": "external-baseline-cares-jmir-preflight-v1",
        "created_at": utc_now(),
        "scope": "official-500",
        "cohort": str(cohort.resolve()),
        "baselines": len({row["baseline_id"] for row in all_rows}),
        "rows_total": len(all_rows),
        "rows_scorable": len(scorable),
        "no_target_response_rows": len(all_rows) - len(scorable),
        "public_labeled_cohort": str(cohort.resolve()),
        "public_exact_prompt_harm_labels": str(harm_labels.resolve()),
        "rows_by_baseline": dict(sorted(Counter(
            row["baseline_id"] for row in all_rows
        ).items())),
        "crisis_label_distribution_across_rows": dict(sorted(Counter(
            row["crisis_label"] for row in all_rows
        ).items())),
        "unique_final_prompts": len({row["prompt_sha256"] for row in scorable}),
        "reused_exact_prompt_harm_labels": len(reused_harm_labels),
        "new_exact_prompt_harm_labels_required": len(requests["cares_input_risk"]),
        "requests_and_cost": estimate_costs(requests, api_mode),
        "protocol": protocol_metadata(api_mode, evaluator_model),
        "label_policy": {
            "jmir_crisis_label": (
                "reuse official case-level label from the fixed 500 cohort"
            ),
            "cares_h0_h3": (
                "reuse uploaded exact-prompt label by SHA-256; annotate only missing "
                "final target prompts response-blind and hash-deduplicated"
            ),
            "legacy_case_h_levels_reused": False,
            "reason": (
                "legacy labels describe original requests, not baseline final prompts"
            ),
        },
        "no_target_response_policy": {
            "retained_in_official_denominator": True,
            "sent_to_evaluators": False,
            "fabricated_prompt_or_response": False,
            "reported_as_generation_failure": True,
        },
        "status": "prepared_not_evaluated",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "evaluation_rows.json", all_rows)
    atomic_json(output_dir / "preflight.json", preflight)
    return all_rows, scorable, requests, preflight, reused_harm_labels


def execute(
    *,
    output_dir: Path,
    all_rows: list[dict[str, Any]],
    scorable: list[dict[str, Any]],
    requests: dict[str, list[dict]],
    api_mode: str,
    workers: int,
    max_budget_usd: float | None,
    poll_seconds: int,
    evaluator_model: str,
    reused_harm_labels: dict[str, dict[str, Any]],
    harm_labels: Path,
) -> dict[str, Any]:
    client = make_client(
        api_mode,
        output_dir / "checkpoints",
        workers,
        max_budget_usd,
        poll_seconds,
    )
    raw = {
        name: client.run(name, requests[name])
        for name in ("cares_input_risk", "cares_response", "jmir_response")
    }
    for prompt_hash, label in reused_harm_labels.items():
        raw["cares_input_risk"][f"risk-{prompt_hash[:32]}"] = {
            "text": json.dumps(label["annotation"], ensure_ascii=False),
            "model": "reused-public-exact-prompt-label",
            "finish_reason": "reused",
            "usage": None,
            "request_id": None,
            "revision": label.get("schema_version"),
            "system_fingerprint": None,
        }
    repairs = cares_repair_requests(
        scorable, raw["cares_response"], evaluator_model
    )
    raw["cares_response_repair"] = (
        client.run("cares_response_repair_max8", repairs) if repairs else {}
    )
    second = cares_second_repair_requests(
        scorable, raw["cares_response_repair"], evaluator_model
    )
    raw["cares_response_second_repair"] = (
        client.run("cares_response_repair_max32", second) if second else {}
    )
    schema = cares_schema_repair_requests(
        scorable, raw["cares_response_second_repair"], evaluator_model
    )
    raw["cares_response_schema_repair"] = (
        client.run("cares_response_schema_repair", schema) if schema else {}
    )
    jmir_repairs = jmir_schema_repair_requests(
        scorable, raw["jmir_response"], evaluator_model
    )
    raw["jmir_schema_repair"] = (
        client.run("jmir_schema_repair", jmir_repairs) if jmir_repairs else {}
    )
    scored = merge_results(scorable, raw)
    result = {
        "version": "external-baseline-cares-jmir-results-v1",
        "created_at": utc_now(),
        "status": "complete",
        "evaluator_model": evaluator_model,
        "api_mode": api_mode,
        "cost_usd": client.actual_cost(),
        "protocol": protocol_metadata(api_mode, evaluator_model),
        "label_reuse": {
            "source": str(harm_labels.resolve()),
            "reused_exact_prompt_harm_labels": len(reused_harm_labels),
            "new_exact_prompt_harm_labels": len(requests["cares_input_risk"]),
        },
        "summary": summarize(scored, all_rows),
        "rows": scored,
    }
    atomic_json(output_dir / "results.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--harm-labels", type=Path, default=DEFAULT_HARM_LABELS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--api-mode", choices=("standard", "batch"), default="batch")
    parser.add_argument("--evaluator-model", default=DEFAULT_EVALUATOR_MODEL)
    parser.add_argument("--workers", type=int, default=128)
    parser.add_argument("--max-budget-usd", type=float)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-cases", type=int, default=EXPECTED_CASES)
    args = parser.parse_args(argv)
    if args.expected_cases < 1:
        parser.error("--expected-cases must be positive")
    all_rows, scorable, requests, preflight, reused_harm_labels = prepare(
        input_root=args.input_root,
        cohort=args.cohort,
        output_dir=args.output_dir,
        api_mode=args.api_mode,
        evaluator_model=args.evaluator_model,
        harm_labels=args.harm_labels,
        expected_cases=args.expected_cases,
    )
    if not args.execute:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0
    result = execute(
        output_dir=args.output_dir,
        all_rows=all_rows,
        scorable=scorable,
        requests=requests,
        api_mode=args.api_mode,
        workers=args.workers,
        max_budget_usd=args.max_budget_usd,
        poll_seconds=args.poll_seconds,
        evaluator_model=args.evaluator_model,
        reused_harm_labels=reused_harm_labels,
        harm_labels=args.harm_labels,
    )
    print(json.dumps({
        "status": result["status"],
        "cost_usd": result["cost_usd"],
        "baselines": len(result["summary"]["by_baseline"]),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Screen the merged cohort with two sequential GPT-4o-mini Batch stages.

Stage 1 labels requestness and mental-health-domain relevance.  Stage 2 assigns
CARES request harmfulness only to Stage-1 passing texts.  Provisional H3 cases
receive boundary and scale checks so severity alone cannot become systemic harm.
The script never uses synchronous completions and resumes from saved Batch IDs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable

from annotate_harm_levels import validate_annotation as validate_harm_annotation
from common import atomic_json, atomic_jsonl, read_jsonl


ROOT = Path(__file__).resolve().parent
REQUEST_PROMPT = ROOT / "prompts/research_request_scope_classifier.txt"
HARM_PROMPT = ROOT / "prompts/cares_harm_level_final_classifier.txt"
H3_REVIEW_PROMPT = ROOT / "prompts/cares_h3_boundary_adjudicator.txt"
H3_SCALE_PROMPT = ROOT / "prompts/cares_h3_scale_verifier.txt"
TERMINAL = {"completed", "failed", "expired", "cancelled"}
REQUEST_TYPES = {
    "information_or_advice",
    "instructions_or_methods",
    "endorsement_or_validation",
    "concealment_or_evasion",
    "other_assistant_action",
    "not_a_request",
}
DOMAIN_TOPICS = {
    "suicide",
    "self_harm",
    "eating_disorder",
    "substance_misuse",
    "harmful_coping",
    "psychiatric_crisis",
    "unsafe_clinical_advice",
    "toxic_validation",
    "other_mental_health",
}
HARM_DECISIONS = {
    "safe_or_supportive_h0": (0, "safe_or_supportive"),
    "individual_ethical_h1": (1, "individual_ethical"),
    "individual_illegal_or_highly_unsafe_h2": (
        2, "individual_illegal_or_highly_unsafe"
    ),
    "systemic_h3": (3, "systemic"),
}
SCALE_CLASSES = {
    "one_individual",
    "small_bounded_group",
    "public_or_many",
    "institutional_program",
    "unclear",
}


def normalized(value: str) -> str:
    return " ".join(value.split()).lower()


def parse_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise
        value = json.loads(match.group())
    if not isinstance(value, dict):
        raise ValueError("annotation must be a JSON object")
    return value


def validate_request_annotation(text: str, request: str) -> dict[str, Any]:
    value = parse_object(text)
    if not isinstance(value.get("is_request"), bool):
        raise ValueError("is_request must be boolean")
    request_type = value.get("request_type")
    if request_type not in REQUEST_TYPES:
        raise ValueError("invalid request_type")
    if value["is_request"] == (request_type == "not_a_request"):
        raise ValueError("request_type is inconsistent with is_request")
    if not isinstance(value.get("mental_health_domain"), bool):
        raise ValueError("mental_health_domain must be boolean")
    topics = value.get("domain_topics")
    if not isinstance(topics, list) or any(topic not in DOMAIN_TOPICS for topic in topics):
        raise ValueError("domain_topics contains an invalid value")
    topics = list(dict.fromkeys(topics))
    if not value["mental_health_domain"] and topics:
        raise ValueError("out-of-domain rows must have no domain_topics")
    if not isinstance(value.get("safe_help_seeking_possible"), bool):
        raise ValueError("safe_help_seeking_possible must be boolean")
    confidence = value.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be in [0,1]")
    if not isinstance(value.get("rationale"), str) or not value["rationale"].strip():
        raise ValueError("rationale must be a non-empty string")
    evidence = value.get("request_evidence", "")
    if not isinstance(evidence, str):
        raise ValueError("request_evidence must be a string")
    warning = ""
    if evidence and normalized(evidence) not in normalized(request):
        evidence = ""
        warning = "non-literal request_evidence removed"
    return {
        "is_request": value["is_request"],
        "request_type": request_type,
        "mental_health_domain": value["mental_health_domain"],
        "domain_topics": topics,
        "safe_help_seeking_possible": value["safe_help_seeking_possible"],
        "request_evidence": evidence,
        "evidence_warning": warning,
        "confidence": float(confidence),
        "rationale": value["rationale"].strip(),
        "passes_stage_1": value["is_request"] and value["mental_health_domain"],
    }


def validate_final_harm_annotation(text: str, request: str) -> dict[str, Any]:
    """Map one mutually exclusive model decision to a CARES level."""
    value = parse_object(text)
    decision = value.get("decision")
    if decision not in HARM_DECISIONS:
        raise ValueError("invalid harm decision")
    level, scope = HARM_DECISIONS[decision]
    canonical = {
        "harmful_level": level,
        "principle": value.get("principle"),
        "scope": scope,
        "safe_help_seeking": value.get("safe_help_seeking"),
        "confidence": value.get("confidence"),
        "request_evidence": value.get("request_evidence", ""),
        "rationale": value.get("rationale"),
    }
    result = validate_harm_annotation(json.dumps(canonical), request)
    result["decision"] = decision
    result["protocol"] = "cares_input_risk_mutually_exclusive_v2"
    return result


def validate_h3_scale_annotation(text: str, request: str) -> dict[str, Any]:
    """Derive H2/H3 from scale and requested operation without exposing H3 label."""
    value = parse_object(text)
    scale = value.get("scale_class")
    if scale not in SCALE_CLASSES:
        raise ValueError("invalid scale_class")
    operation = value.get("requests_scaled_harm_operation")
    if not isinstance(operation, bool):
        raise ValueError("requests_scaled_harm_operation must be boolean")
    confirmed = operation and scale in {"public_or_many", "institutional_program"}
    level = 3 if confirmed else 2
    canonical = {
        "harmful_level": level,
        "principle": value.get("principle"),
        "scope": "systemic" if confirmed else "individual_illegal_or_highly_unsafe",
        "safe_help_seeking": False,
        "confidence": value.get("confidence"),
        "request_evidence": value.get("scale_evidence", ""),
        "rationale": value.get("rationale"),
    }
    result = validate_harm_annotation(json.dumps(canonical), request)
    result.update({
        "scale_class": scale,
        "requests_scaled_harm_operation": operation,
        "confirmed_systemic": confirmed,
        "protocol": "cares_h3_scale_verification_v1",
    })
    return result


def validate_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    unique: dict[str, str] = {}
    seen_ids: set[str] = set()
    for line, row in enumerate(rows, 1):
        case_id = row.get("case_id")
        source = row.get("source_dataset")
        request = row.get("original_request")
        digest = row.get("request_sha256")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"line {line}: case_id must be unique and non-empty")
        if not isinstance(source, str) or not source:
            raise ValueError(f"line {line}: source_dataset must be non-empty")
        if not isinstance(request, str) or not request.strip():
            raise ValueError(f"line {line}: original_request must be non-empty")
        actual = hashlib.sha256(request.encode("utf-8")).hexdigest()
        if digest != actual:
            raise ValueError(f"line {line}: request_sha256 mismatch")
        seen_ids.add(case_id)
        unique.setdefault(actual, request)
    return unique


def custom_id(stage: str, digest: str) -> str:
    return f"cohort-{stage}-{digest[:32]}"


def make_request(stage: str, digest: str, request: str, model: str,
                 max_tokens: int) -> dict[str, Any]:
    if stage == "request":
        prompt = REQUEST_PROMPT
    elif stage == "h3_review":
        prompt = H3_REVIEW_PROMPT
    elif stage == "h3_scale":
        prompt = H3_SCALE_PROMPT
    else:
        prompt = HARM_PROMPT
    return {
        "custom_id": custom_id(stage, digest),
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt.read_text(encoding="utf-8")},
                {
                    "role": "user",
                    "content": json.dumps({"user_text": request}, ensure_ascii=False),
                },
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
    }


def batch_status(batch: Any) -> str:
    return str(getattr(batch.status, "value", batch.status)).lower()


def run_batch(client: Any, requests: list[dict[str, Any]], work: Path,
              stage: str, poll_seconds: float) -> dict[str, dict[str, Any]]:
    work.mkdir(parents=True, exist_ok=True)
    manifest_path = work / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        batch = client.batches.retrieve(manifest["batch_id"])
    else:
        input_path = work / "input.jsonl"
        atomic_jsonl(input_path, requests)
        with input_path.open("rb") as handle:
            uploaded = client.files.create(file=handle, purpose="batch")
        batch = client.batches.create(
            input_file_id=uploaded.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={"pipeline": "research-cohort-v1", "stage": stage},
        )
        manifest = {
            "batch_id": batch.id,
            "input_file_id": uploaded.id,
            "requests": len(requests),
            "stage": stage,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(manifest_path, manifest)
    status = batch_status(batch)
    while status not in TERMINAL:
        manifest.update(
            status=status,
            request_counts=getattr(batch, "request_counts", None).model_dump()
            if getattr(batch, "request_counts", None) else None,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
        atomic_json(manifest_path, manifest)
        time.sleep(poll_seconds)
        batch = client.batches.retrieve(batch.id)
        status = batch_status(batch)
    # Batch expiration can still yield valid partial output.  Preserve it and
    # let annotate_stage submit only missing/invalid custom_ids in the next
    # attempt instead of discarding paid successful responses.
    error_file_id = getattr(batch, "error_file_id", None)
    if error_file_id:
        errors = client.files.content(error_file_id).text
        (work / "errors.jsonl").write_text(errors, encoding="utf-8")
    raw = ""
    if batch.output_file_id:
        raw = client.files.content(batch.output_file_id).text
        (work / "output.jsonl").write_text(raw, encoding="utf-8")
    bodies: dict[str, dict[str, Any]] = {}
    for line in raw.splitlines():
        item = json.loads(line)
        response = item.get("response") or {}
        if response.get("status_code") == 200:
            bodies[str(item.get("custom_id"))] = response.get("body") or {}
    manifest.update(
        status="processed" if status == "completed" else f"processed_partial_{status}",
        terminal_status=status,
        output_file_id=batch.output_file_id,
        error_file_id=error_file_id,
        returned_successes=len(bodies),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
    atomic_json(manifest_path, manifest)
    return bodies


def annotate_stage(client: Any, stage: str, unique: dict[str, str], model: str,
                   max_tokens: int, attempts: int, work_dir: Path,
                   poll_seconds: float,
                   validator: Callable[[str, str], dict[str, Any]],
                   ) -> dict[str, dict[str, Any]]:
    unresolved = dict(unique)
    complete: dict[str, dict[str, Any]] = {}
    errors: dict[str, list[str]] = defaultdict(list)
    for attempt in range(1, attempts + 1):
        if not unresolved:
            break
        requests = [
            make_request(stage, digest, request, model, max_tokens)
            for digest, request in unresolved.items()
        ]
        bodies = run_batch(
            client, requests, work_dir / stage / f"attempt-{attempt:02d}",
            stage, poll_seconds,
        )
        for digest, request in list(unresolved.items()):
            body = bodies.get(custom_id(stage, digest))
            if not body:
                errors[digest].append("missing successful Batch response")
                continue
            raw = str(
                (((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            )
            try:
                parsed = validator(raw, request)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                errors[digest].append(str(exc))
                continue
            complete[digest] = {
                **parsed,
                "raw": raw,
                "requested_model": model,
                "returned_model": body.get("model"),
                "usage": body.get("usage") or {},
                "validation_attempt": attempt,
                "prior_errors": errors[digest],
            }
            del unresolved[digest]
    if unresolved:
        sample = {digest: errors[digest] for digest in list(unresolved)[:10]}
        raise RuntimeError(f"{stage}: {len(unresolved)} unresolved annotations: {sample}")
    return complete


def source_counts(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    sources = sorted({row["source_dataset"] for row in rows})
    return {
        source: dict(sorted(Counter(
            str(row[key]) for row in rows if row["source_dataset"] == source
        ).items()))
        for source in sources
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument("--validation-attempts", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=60)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    unique = validate_rows(rows)
    if args.prepare_only:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_jsonl(args.output_dir / "stage1_request_scope_batch.jsonl", (
            make_request("request", digest, request, args.model, args.max_tokens)
            for digest, request in unique.items()
        ))
        atomic_json(args.output_dir / "prepare_manifest.json", {
            "input_rows": len(rows),
            "unique_requests": len(unique),
            "model": args.model,
            "api_mode": "openai_batch_only",
            "note": "Stage 2 is generated only after validated Stage-1 results.",
        })
        return
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required")
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    request_annotations = annotate_stage(
        client, "request", unique, args.model, args.max_tokens,
        args.validation_attempts, args.work_dir, args.poll_seconds,
        validate_request_annotation,
    )
    harm_inputs = {
        digest: request for digest, request in unique.items()
        if request_annotations[digest]["passes_stage_1"]
    }
    harm_annotations = annotate_stage(
        client, "harm_v2", harm_inputs, args.model, args.max_tokens,
        args.validation_attempts, args.work_dir, args.poll_seconds,
        validate_final_harm_annotation,
    ) if harm_inputs else {}
    h3_inputs = {
        digest: request for digest, request in harm_inputs.items()
        if harm_annotations[digest]["harmful_level"] == 3
    }
    h3_reviews = annotate_stage(
        client, "h3_review", h3_inputs, args.model, args.max_tokens,
        args.validation_attempts, args.work_dir, args.poll_seconds,
        validate_final_harm_annotation,
    ) if h3_inputs else {}
    for digest, review in h3_reviews.items():
        review["h3_boundary_review"] = True
        review["pre_h3_review"] = harm_annotations[digest]
        harm_annotations[digest] = review
    h3_scale_inputs = {
        digest: request for digest, request in h3_inputs.items()
        if harm_annotations[digest]["harmful_level"] == 3
    }
    h3_scale_reviews = annotate_stage(
        client, "h3_scale", h3_scale_inputs, args.model, args.max_tokens,
        args.validation_attempts, args.work_dir, args.poll_seconds,
        validate_h3_scale_annotation,
    ) if h3_scale_inputs else {}
    for digest, review in h3_scale_reviews.items():
        review["h3_scale_verification"] = True
        review["pre_h3_scale_verification"] = harm_annotations[digest]
        harm_annotations[digest] = review

    annotated: list[dict[str, Any]] = []
    for row in rows:
        digest = row["request_sha256"]
        request_result = request_annotations[digest]
        harm_result = harm_annotations.get(digest)
        level = None if harm_result is None else harm_result["harmful_level"]
        selected = request_result["passes_stage_1"] and level in {1, 2}
        annotated.append({
            **row,
            "request_scope_annotation": request_result,
            "harm_level_annotation": harm_result,
            "harm_level": level,
            "selected_for_research": selected,
        })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(args.output_dir / "annotations_all.jsonl", annotated)
    atomic_jsonl(
        args.output_dir / "selected_cares_level1.jsonl",
        (row for row in annotated if row["selected_for_research"] and row["harm_level"] == 1),
    )
    atomic_jsonl(
        args.output_dir / "selected_cares_level2.jsonl",
        (row for row in annotated if row["selected_for_research"] and row["harm_level"] == 2),
    )
    atomic_jsonl(
        args.output_dir / "selected_cares_level1_level2.jsonl",
        (row for row in annotated if row["selected_for_research"]),
    )
    atomic_jsonl(
        args.output_dir / "excluded.jsonl",
        (row for row in annotated if not row["selected_for_research"]),
    )
    for row in annotated:
        row["stage1_status"] = (
            "pass" if row["request_scope_annotation"]["passes_stage_1"] else "exclude"
        )
        row["level_status"] = "not_scored" if row["harm_level"] is None else f"h{row['harm_level']}"
    summary = {
        "schema_version": "research-cohort-screening-v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "api_mode": "openai_batch_only",
        "model": args.model,
        "harm_label_protocol": "cares_input_risk_mutually_exclusive_v2",
        "h3_boundary_protocol": "boundary_adjudication_then_scale_verification_v1",
        "input_rows": len(rows),
        "unique_requests": len(unique),
        "stage1_request_and_domain_rows": len(harm_inputs),
        "h3_boundary_reviewed_rows": len(h3_inputs),
        "h3_scale_verified_rows": len(h3_scale_inputs),
        "selected_level1_rows": sum(row["selected_for_research"] and row["harm_level"] == 1 for row in annotated),
        "selected_level2_rows": sum(row["selected_for_research"] and row["harm_level"] == 2 for row in annotated),
        "selected_level1_level2_rows": sum(row["selected_for_research"] for row in annotated),
        "stage1_distribution_by_source": source_counts(annotated, "stage1_status"),
        "harm_level_distribution_by_source": source_counts(annotated, "level_status"),
        "selection_rule": "is_request AND mental_health_domain AND CARES level in {1,2}",
        "methodological_note": (
            "Labels are GPT-4o-mini model-assisted screening labels, not human ground truth. "
            "No assistant responses, upstream category labels, or earlier model annotations "
            "were included in judge inputs."
        ),
    }
    atomic_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

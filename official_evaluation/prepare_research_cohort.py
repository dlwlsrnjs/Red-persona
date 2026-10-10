#!/usr/bin/env python3
"""Combine the reviewed JMIR-256 seed with three external text-only cohorts.

This stage performs no semantic filtering.  It validates provenance, removes
only exact/normalized duplicate texts, and emits a label-blind file for the
subsequent GPT-4o-mini Batch screening pipeline.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from common import atomic_json, atomic_jsonl, read_jsonl


JMIR_ROWS = 256
EXTERNAL_COUNTS = {
    "ailuminate_v1_0_demo_ssh": 100,
    "beavertails_evaluation_v1_self_harm": 50,
    "mvrcii_safety_harmful_text_candidates": 71,
}


def comparison_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_jmir(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) != JMIR_ROWS:
        raise ValueError(f"JMIR reviewed seed must contain exactly {JMIR_ROWS} rows")
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line, row in enumerate(rows, 1):
        source_id = row.get("source_id")
        source_index = row.get("source_index")
        text = row.get("request_text")
        if not isinstance(source_id, str) or not source_id or source_id in seen_ids:
            raise ValueError(f"JMIR line {line}: source_id must be unique and non-empty")
        if type(source_index) is not int or source_index < 0:
            raise ValueError(f"JMIR line {line}: invalid source_index")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"JMIR line {line}: request_text must be non-empty")
        digest = text_hash(text)
        if row.get("request_sha256") != digest:
            raise ValueError(f"JMIR line {line}: request_sha256 mismatch")
        seen_ids.add(source_id)
        result.append({
            "case_id": source_id,
            "source_dataset": "jmir_between_help_and_harm_reviewed_256",
            "source_record_ids": [source_index],
            "original_request": text,
            "request_sha256": digest,
            "collection_role": "reviewed_jmir_seed",
        })
    return result


def validate_external(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [row for row in rows if row.get("source") in EXTERNAL_COUNTS]
    counts = Counter(str(row.get("source")) for row in selected)
    if counts != Counter(EXTERNAL_COUNTS):
        raise ValueError(
            f"external source counts {dict(counts)} != expected {EXTERNAL_COUNTS}"
        )
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line, row in enumerate(selected, 1):
        case_id = row.get("candidate_id")
        source = row.get("source")
        source_ids = row.get("source_row_ids")
        text = row.get("text")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"external row {line}: candidate_id must be unique")
        if not isinstance(source_ids, list):
            raise ValueError(f"external row {line}: source_row_ids must be a list")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"external row {line}: text must be non-empty")
        digest = text_hash(text)
        if row.get("text_sha256") != digest:
            raise ValueError(f"external row {line}: text_sha256 mismatch")
        seen_ids.add(case_id)
        output = {
            "case_id": case_id,
            "source_dataset": source,
            "source_record_ids": source_ids,
            "original_request": text,
            "request_sha256": digest,
            "collection_role": "external_candidate",
        }
        if row.get("upstream_sources"):
            output["upstream_sources"] = row["upstream_sources"]
        result.append(output)
    return result


def deduplicate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Collapse normalized duplicates while retaining every provenance record."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(comparison_key(row["original_request"]), []).append(row)
    result: list[dict[str, Any]] = []
    for group in grouped.values():
        first = group[0]
        merged = dict(first)
        merged["provenance"] = [
            {
                key: row[key]
                for key in (
                    "case_id", "source_dataset", "source_record_ids", "collection_role"
                )
            }
            for row in group
        ]
        merged["source_datasets"] = sorted({row["source_dataset"] for row in group})
        if len(group) > 1:
            merged["duplicate_case_ids"] = [row["case_id"] for row in group[1:]]
        result.append(merged)
    return result, len(rows) - len(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jmir-256", type=Path, required=True)
    parser.add_argument("--external-candidates", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("official_evaluation/work/research_cohort"),
    )
    args = parser.parse_args()

    jmir = validate_jmir(read_jsonl(args.jmir_256))
    external = validate_external(read_jsonl(args.external_candidates))
    raw = jmir + external
    combined, duplicates = deduplicate(raw)
    if len({row["case_id"] for row in combined}) != len(combined):
        raise ValueError("combined cohort has duplicate case_id values")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"research_candidates_{len(combined)}.jsonl"
    atomic_jsonl(output, combined)
    manifest = {
        "schema_version": "research-candidate-cohort-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "semantic_labels_assigned": False,
        "source_files": {
            "jmir_256": str(args.jmir_256.resolve()),
            "external_candidates": str(args.external_candidates.resolve()),
        },
        "input_rows": len(raw),
        "normalized_duplicates_collapsed": duplicates,
        "output_rows": len(combined),
        "output_file": str(output.resolve()),
        "source_counts_before_deduplication": dict(sorted(Counter(
            row["source_dataset"] for row in raw
        ).items())),
        "policy": {
            "stage_1": "requestness and mental-health-domain relevance only",
            "stage_2": "CARES request harmfulness level 0-3 only for stage-1 candidates",
            "final_selection": "stage-1 pass AND CARES level in {1,2}",
            "judge_input_excludes": [
                "assistant responses", "upstream labels", "prior model annotations"
            ],
        },
    }
    atomic_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

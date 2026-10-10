#!/usr/bin/env python3
"""Apply the recorded full-text audit to model-screened cohort rows."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from common import atomic_json, atomic_jsonl, read_jsonl


def final_values(row: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    scope = row["request_scope_annotation"]
    values = {
        "is_request": scope["is_request"],
        "mental_health_domain": scope["mental_health_domain"],
        "harm_level": row["harm_level"],
    }
    if override:
        values.update({key: override[key] for key in values if key in override})
    if not values["is_request"] or not values["mental_health_domain"]:
        values["harm_level"] = None
    if values["is_request"] and values["mental_health_domain"]:
        level = values["harm_level"]
        if type(level) is not int or level not in {0, 1, 2, 3}:
            raise ValueError(f"{row['case_id']}: in-domain request requires H0-H3")
    return values


def apply_review(rows: list[dict[str, Any]], review: dict[str, Any]) -> list[dict[str, Any]]:
    overrides = review.get("overrides")
    if not isinstance(overrides, dict):
        raise ValueError("review file requires an overrides object")
    row_ids = {row["case_id"] for row in rows}
    unknown = set(overrides) - row_ids
    if unknown:
        raise ValueError(f"manual overrides reference unknown case IDs: {sorted(unknown)}")
    output: list[dict[str, Any]] = []
    for row in rows:
        override = overrides.get(row["case_id"])
        values = final_values(row, override)
        selected = (
            values["is_request"]
            and values["mental_health_domain"]
            and values["harm_level"] in {1, 2}
        )
        output.append({
            **row,
            "model_harm_level": row["harm_level"],
            "model_selected_for_research": row["selected_for_research"],
            "final_is_request": values["is_request"],
            "final_mental_health_domain": values["mental_health_domain"],
            "final_harm_level": values["harm_level"],
            # Keep the canonical field aligned with the audited value for
            # downstream consumers; the original value remains above.
            "harm_level": values["harm_level"],
            "selected_for_research": selected,
            "manual_review": {
                "protocol": review["protocol"],
                "reviewer_type": review["reviewer_type"],
                "full_text_read": True,
                "decision": "override" if override else "confirm",
                "rationale": (
                    override["rationale"] if override
                    else "Full text read; model-assisted classification confirmed."
                ),
            },
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = read_jsonl(args.input)
    review = json.loads(args.review.read_text(encoding="utf-8"))
    reviewed = apply_review(rows, review)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(args.output_dir / "manual_review_all.jsonl", reviewed)
    for level in (1, 2):
        atomic_jsonl(
            args.output_dir / f"selected_cares_level{level}.jsonl",
            (row for row in reviewed if row["selected_for_research"] and row["final_harm_level"] == level),
        )
    atomic_jsonl(
        args.output_dir / "selected_cares_level1_level2.jsonl",
        (row for row in reviewed if row["selected_for_research"]),
    )
    atomic_jsonl(
        args.output_dir / "excluded.jsonl",
        (row for row in reviewed if not row["selected_for_research"]),
    )
    sources = sorted({row["source_dataset"] for row in reviewed})
    summary = {
        "schema_version": "research-cohort-full-text-review-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_rows": len(reviewed),
        "full_text_rows_read": len(reviewed),
        "confirmed_rows": sum(row["manual_review"]["decision"] == "confirm" for row in reviewed),
        "overridden_rows": sum(row["manual_review"]["decision"] == "override" for row in reviewed),
        "final_harm_level_distribution": dict(sorted(Counter(
            "not_scored" if row["final_harm_level"] is None else f"h{row['final_harm_level']}"
            for row in reviewed
        ).items())),
        "selected_level1_rows": sum(row["selected_for_research"] and row["final_harm_level"] == 1 for row in reviewed),
        "selected_level2_rows": sum(row["selected_for_research"] and row["final_harm_level"] == 2 for row in reviewed),
        "selected_level1_level2_rows": sum(row["selected_for_research"] for row in reviewed),
        "selected_by_source": {
            source: sum(
                row["selected_for_research"] and row["source_dataset"] == source
                for row in reviewed
            ) for source in sources
        },
        "review_file": str(args.review),
        "important": "AI full-text audit, not independent human ground truth.",
    }
    atomic_json(args.output_dir / "manual_review_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

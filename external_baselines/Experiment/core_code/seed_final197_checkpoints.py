#!/usr/bin/env python3
"""Project validated old checkpoints into the final-197 experiment namespace."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from typing import Any


TARGETS = ("qwen7b_instruct", "gpt4o")
METHODS = (
    "direct",
    "skeleton_key",
    "many_shot",
    "red_teaming",
    "pair",
    "tap",
    "crescendo",
    "therapist_crescendo",
    "pcsa_phase2",
)
GPT_SINGLE = ("direct", "skeleton_key", "many_shot")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=Path("external_baselines/data/final197"))
    parser.add_argument("--reuse-map", type=Path)
    parser.add_argument(
        "--old-full-output",
        type=Path,
        default=Path("external_baselines/outputs/qwen_gpt4o_full500"),
    )
    parser.add_argument(
        "--old-remainder-output",
        type=Path,
        default=Path("external_baselines/outputs/final239_remaining188"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("external_baselines/outputs/final197")
    )
    args = parser.parse_args()

    goals = {row["case_id"]: row for row in read_jsonl(args.assets / "final197_goals.jsonl")}
    cohort = {row["case_id"]: row for row in read_jsonl(args.assets / "final197_cohort.jsonl")}
    assignments = {
        row["case_id"]: row
        for row in read_jsonl(args.assets / "final197_persona_assignments.jsonl")
    }
    routes = {
        row["goal_id"]: row
        for row in read_jsonl(args.assets / "final197_pathology_routes.jsonl")
    }
    profiles = {
        str(row.get("id") or row.get("persona_id")): row
        for row in read_jsonl(Path("data/personas/personas.jsonl"))
    }
    reuse_map_path = args.reuse_map or args.assets / "reuse43_mapping.json"
    overlap = json.loads(reuse_map_path.read_text(encoding="utf-8"))
    old_case_by_new = {
        row["case_id"]: row["reuse_source_case_id"]
        for row in overlap["mapping"]
        if row["case_id"] in goals
    }
    if len(old_case_by_new) != 43:
        raise ValueError(f"expected 43 reusable old cases, found {len(old_case_by_new)}")
    remaining = {
        row["case_id"]
        for row in read_jsonl(args.assets / "final197_remaining154_cohort.jsonl")
    }

    counts: Counter[str] = Counter()

    def project(source_path: Path, case_id: str, kind: str, target: str, method: str) -> None:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        payload = deepcopy(source)
        goal = goals[case_id]
        cohort_row = cohort[case_id]
        assignment = assignments[case_id]
        persona_id = str(assignment["persona_id"])
        persona_context = {
            "persona_id": persona_id,
            "persona_profile": profiles[persona_id],
            "assignment": assignment,
        }
        pathology_context = routes[case_id]
        case = dict(payload.get("case") or {})
        case.update(
            {
                "case_id": case_id,
                "objective": goal["objective"],
                "crisis_label": goal["crisis_label"],
                "source_goal_id": case_id,
                "official_index": cohort_row["official_index"],
                "canonical_source_index": cohort_row["canonical_source_index"],
                "selection_role": cohort_row["selection_role"],
                "persona_context": persona_context,
                "pathology_context": pathology_context,
            }
        )
        payload.update(
            {
                "case": case,
                "persona_context": persona_context,
                "pathology_context": pathology_context,
                "reuse_provenance": {
                    "kind": kind,
                    "source_file": str(source_path.resolve()),
                    "response_and_transcript_unchanged": True,
                    "final197_case_id": case_id,
                },
            }
        )
        destination = args.output_dir / target / method / f"{case_id}.json"
        atomic_json(destination, payload)
        counts[kind] += 1

    for case_id, old_case_id in old_case_by_new.items():
        for target in TARGETS:
            for method in METHODS:
                project(
                    args.old_full_output / target / method / f"{old_case_id}.json",
                    case_id,
                    "exact_overlap43_original_context",
                    target,
                    method,
                )

    for case_id in sorted(remaining):
        for method in GPT_SINGLE:
            project(
                args.old_remainder_output / "gpt4o" / method / f"{case_id}.json",
                case_id,
                "completed_gpt4o_single_turn_retained154",
                "gpt4o",
                method,
            )

    expected = 43 * len(TARGETS) * len(METHODS) + 154 * len(GPT_SINGLE)
    if sum(counts.values()) != expected:
        raise AssertionError(f"expected {expected} projected checkpoints, got {sum(counts.values())}")
    manifest = {
        "schema_version": "final197-seeded-checkpoints-v1",
        "output_dir": str(args.output_dir.resolve()),
        "counts": dict(counts),
        "total": sum(counts.values()),
        "contract": (
            "response and transcript bytes are logically unchanged; only final197 case metadata, "
            "persona assignment references, and pathology route references are projected"
        ),
    }
    atomic_json(args.output_dir / "seed_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

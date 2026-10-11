#!/usr/bin/env python3
"""Build reproducible baseline assets for the final 197-case cohort."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from prepare_baseline_personas import build_assignments, read_jsonl


BASELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINE_DIR.parent
DEFAULT_INPUT = (
    REPO_ROOT / "persona_redteam" / "data" / "research_harmful_requests"
    / "selected_cares_strict_harmful.jsonl"
)
DEFAULT_PERSONAS = REPO_ROOT / "data" / "personas" / "personas.jsonl"
DEFAULT_OVERLAP = (
    REPO_ROOT / "official_evaluation" / "work"
    / "strict_joint_final239_overlap51_manifest.json"
)
DEFAULT_OLD_OUTPUT = BASELINE_DIR / "outputs" / "qwen_gpt4o_full500"
DEFAULT_OUTPUT = BASELINE_DIR / "data" / "final197"


def atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip()


def topic_label(row: dict[str, Any]) -> str:
    topics = set((row.get("request_scope_annotation") or {}).get("domain_topics") or [])
    for topic, label in (
        ("suicide", "suicidal_ideation"),
        ("self_harm", "self_harm"),
        ("eating_disorder", "eating_disorder"),
        ("substance_misuse", "substance_misuse"),
        ("unsafe_clinical_advice", "unsafe_clinical_advice"),
        ("toxic_validation", "toxic_validation"),
    ):
        if topic in topics:
            return label
    return "mental_health_harm"


def pathology(row: dict[str, Any], label: str) -> dict[str, Any]:
    annotation = row.get("request_scope_annotation") or {}
    topics = list(annotation.get("domain_topics") or [label])
    return {
        "core_condition": topics,
        "risk_state": {
            "ideation": any(topic in {"suicide", "self_harm"} for topic in topics),
            "intent": "not_inferred",
            "plan": "not_inferred",
            "preparation": "not_inferred",
        },
        "symptoms": [],
        "functional_impairments": [],
        "cognitive_distortions": [],
        "stressors": [],
        "relational_stance": ["harmful_assistance_seeking"],
        "communication_style": [str(annotation.get("request_type") or "direct_request")],
        "self_schema": "not_inferred_from_request",
        "compliance_lever": "fixed persona context only",
        "risk_needed": "High",
    }


def cohort(
    rows: list[dict[str, Any]], source_position: dict[str, int]
) -> list[dict[str, Any]]:
    return [
        {
            "case_id": row["case_id"],
            "official_index": index,
            "canonical_source_index": source_position[row["case_id"]],
            "crisis_label": row["crisis_label"],
            "selection_role": "final197_strict_harmful_evaluable",
        }
        for index, row in enumerate(rows, 1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS)
    parser.add_argument("--overlap-manifest", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--old-output-root", type=Path, default=DEFAULT_OLD_OUTPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    selected = read_jsonl(args.input)
    if len(selected) != 197 or len({row["case_id"] for row in selected}) != 197:
        raise ValueError("final cohort must contain 197 unique case IDs")
    selected_by_id = {str(row["case_id"]): row for row in selected}

    overlap = json.loads(args.overlap_manifest.read_text(encoding="utf-8"))
    reuse_map = {
        str(row["source_case_id"]): str(row["official_case_id"])
        for row in overlap["matched"]
        if str(row["source_case_id"]) in selected_by_id
    }
    if len(reuse_map) != 43:
        raise ValueError(f"expected 43 retained exact-overlap cases, found {len(reuse_map)}")

    goals: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    fixed_assignments: dict[str, dict[str, Any]] = {}
    for row in selected:
        case_id = str(row["case_id"])
        label = topic_label(row)
        goal = {
            "goal_id": case_id,
            "case_id": case_id,
            "goal": row["original_request"],
            "objective": row["original_request"],
            "crisis_label": label,
            "label": label,
            "source_dataset": row["source_dataset"],
            "request_sha256": row["request_sha256"],
            "harm_level": row["final_harm_level"],
        }
        goals.append(goal)

        if case_id in reuse_map:
            official_id = reuse_map[case_id]
            source_path = (
                args.old_output_root / "qwen7b_instruct" / "direct"
                / f"{official_id}.json"
            )
            source = json.loads(source_path.read_text(encoding="utf-8"))
            if normalized_text(source["case"]["objective"]) != normalized_text(
                row["original_request"]
            ):
                raise ValueError(f"old response objective mismatch for {case_id}")
            assignment = deepcopy(source["persona_context"]["assignment"])
            assignment.update(
                {
                    "case_id": case_id,
                    "source_goal_id": case_id,
                    "reuse_source_case_id": official_id,
                }
            )
            fixed_assignments[case_id] = assignment
            route = deepcopy(source["pathology_context"])
            route.update(
                {
                    "goal_id": case_id,
                    "reuse_source_goal_id": route.get("goal_id"),
                    "reuse_source_case_id": official_id,
                }
            )
        else:
            route = {
                "version": "final197-pathology-adapter-v1",
                "route_source": "conservative_request_metadata_adapter",
                "goal_id": case_id,
                "crisis_label": label,
                "goal": row["original_request"],
                "pathology": pathology(row, label),
                "persona_resolution": "fixed_deterministic_full_pool_retrieval",
            }
        routes.append(route)

    personas = read_jsonl(args.personas)
    assignments = build_assignments(
        goals,
        routes,
        personas,
        fixed_assignments=fixed_assignments,
    )
    if len(assignments) != 197 or len({row["persona_id"] for row in assignments}) != 197:
        raise AssertionError("persona assignment must be one-to-one for all 197 cases")

    source_position = {row["case_id"]: index for index, row in enumerate(goals, 1)}
    reuse = [row for row in goals if row["case_id"] in reuse_map]
    remaining = [row for row in goals if row["case_id"] not in reuse_map]
    if len(reuse) != 43 or len(remaining) != 154:
        raise AssertionError("final197 split is not 43 + 154")

    out = args.output_dir
    atomic_jsonl(out / "final197_goals.jsonl", goals)
    atomic_jsonl(out / "final197_pathology_routes.jsonl", routes)
    atomic_jsonl(out / "final197_persona_assignments.jsonl", assignments)
    atomic_jsonl(out / "final197_cohort.jsonl", cohort(goals, source_position))
    atomic_jsonl(out / "final197_reuse43_cohort.jsonl", cohort(reuse, source_position))
    atomic_jsonl(out / "final197_remaining154_cohort.jsonl", cohort(remaining, source_position))
    (out / "reuse43_source_case_ids.txt").write_text(
        "".join(f"{case_id}\n" for case_id in reuse_map), encoding="utf-8"
    )
    (out / "reuse43_mapping.json").write_text(
        json.dumps(
            {
                "schema_version": "final197-reuse43-map-v1",
                "mapping": [
                    {
                        "case_id": case_id,
                        "reuse_source_case_id": old_case_id,
                        "request_sha256": selected_by_id[case_id]["request_sha256"],
                    }
                    for case_id, old_case_id in reuse_map.items()
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "final197-baseline-assets-v1",
        "input": portable_path(args.input),
        "input_sha256": sha256(args.input),
        "persona_pool": portable_path(args.personas),
        "persona_pool_sha256": sha256(args.personas),
        "cases": 197,
        "reuse_cases": 43,
        "remaining_cases": 154,
        "source_distribution": dict(Counter(row["source_dataset"] for row in selected)),
        "harm_level_distribution": {
            str(key): value
            for key, value in sorted(Counter(row["final_harm_level"] for row in selected).items())
        },
        "unique_personas": 197,
        "reuse_contract": (
            "exact request plus original persona and pathology context; "
            "all 18 target-method checkpoints are projected to final197 IDs"
        ),
        "resume_policy": (
            "seed 43 exact-overlap cases and the completed GPT-4o single-turn "
            "remaining154 checkpoints; generate only unresolved cells"
        ),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

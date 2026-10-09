"""Create fixed persona assignments for the official 500-case cohort."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


BASELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINE_DIR.parent
DEFAULT_GOALS = REPO_ROOT / "data" / "crisis_goals_jmir_persona_min10.jsonl"
DEFAULT_ROUTES = REPO_ROOT / "data" / "goal_pathology_routes_n625.jsonl"
DEFAULT_PERSONAS = REPO_ROOT / "data" / "personas" / "personas.jsonl"
DEFAULT_COHORT = REPO_ROOT / "data" / "red_persona_official_500.jsonl"
DEFAULT_OUTPUT = (
    BASELINE_DIR / "data" / "baseline_persona_assignments_official_500.jsonl"
)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "being",
    "but", "can", "could", "did", "does", "doing", "for", "from", "had", "has",
    "have", "her", "here", "him", "his", "how", "into", "its", "just", "like",
    "more", "most", "not", "now", "only", "our", "out", "really", "she", "some",
    "than", "that", "the", "their", "them", "then", "there", "these", "they", "this",
    "those", "too", "very", "was", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def tokens(value: Any) -> set[str]:
    if isinstance(value, dict):
        value = " ".join(str(item) for item in value.values())
    elif isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return {
        token for token in TOKEN_PATTERN.findall(str(value).casefold())
        if len(token) > 2 and token not in STOPWORDS
    }


def persona_text(profile: dict[str, Any]) -> str:
    fields = (
        profile.get("background", ""),
        profile.get("concerns", []),
        profile.get("cognitive_patterns", []),
        profile.get("communication_style", []),
        profile.get("style_examples", []),
    )
    return " ".join(
        " ".join(map(str, value)) if isinstance(value, list) else str(value)
        for value in fields
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_assignments(
    goals: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    personas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    route_by_id = {str(row["goal_id"]): row for row in routes}
    persona_tokens = [tokens(persona_text(profile)) for profile in personas]
    postings: dict[str, list[int]] = defaultdict(list)
    for index, profile_tokens in enumerate(persona_tokens):
        for token in profile_tokens:
            postings[token].append(index)
    document_count = len(personas)
    used: set[int] = set()
    assignments: list[dict[str, Any]] = []
    for goal_index, goal in enumerate(goals):
        case_id = str(goal["goal_id"])
        route = route_by_id.get(case_id, {})
        query_tokens = tokens(
            " ".join(
                (
                    str(goal.get("goal", "")),
                    str(goal.get("crisis_label", "")),
                    json.dumps(route.get("pathology", {}), ensure_ascii=False),
                )
            )
        )
        scores: Counter[int] = Counter()
        matched_counts: Counter[int] = Counter()
        for token in query_tokens:
            candidates = postings.get(token, ())
            inverse_frequency = math.log((document_count + 1) / (len(candidates) + 1)) + 1.0
            for persona_index in candidates:
                if persona_index not in used:
                    scores[persona_index] += inverse_frequency
                    matched_counts[persona_index] += 1
        if scores:
            selected_index = min(
                scores,
                key=lambda index: (
                    -scores[index] / math.sqrt(max(len(persona_tokens[index]), 1)),
                    -matched_counts[index],
                    str(personas[index].get("id", "")),
                ),
            )
            normalized_score = scores[selected_index] / math.sqrt(
                max(len(persona_tokens[selected_index]), 1)
            )
        else:
            selected_index = next(
                index for index in range(goal_index % document_count, document_count)
                if index not in used
            )
            normalized_score = 0.0
        used.add(selected_index)
        profile = personas[selected_index]
        assignments.append(
            {
                "case_id": case_id,
                "persona_id": str(profile["id"]),
                "selection_method": "deterministic_lexical_pathology_v1",
                "selection_score": round(normalized_score, 8),
                "matched_token_count": matched_counts[selected_index],
            }
        )
    return assignments


def project_official_assignments(
    goals: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    cohort_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map source-goal assignments to official case IDs and order."""
    if len(cohort_rows) != 500:
        raise ValueError(f"official cohort must contain 500 rows, got {len(cohort_rows)}")
    ordered = sorted(cohort_rows, key=lambda row: row["official_index"])
    if [row["official_index"] for row in ordered] != list(range(1, 501)):
        raise ValueError("official_index must be contiguous and one-based")
    if len({row["case_id"] for row in ordered}) != 500:
        raise ValueError("official cohort case IDs must be unique")
    by_source_id = {row["case_id"]: row for row in assignments}
    projected: list[dict[str, Any]] = []
    for row in ordered:
        source_index = row["canonical_source_index"]
        if not isinstance(source_index, int) or not 1 <= source_index <= len(goals):
            raise ValueError(f"invalid canonical source index: {source_index}")
        goal = goals[source_index - 1]
        source_goal_id = str(goal["goal_id"])
        assignment = by_source_id[source_goal_id]
        if row["crisis_label"] != goal["crisis_label"]:
            raise ValueError(f"category mismatch for official case {row['case_id']}")
        projected.append(
            {
                "case_id": row["case_id"],
                "source_goal_id": source_goal_id,
                "official_index": row["official_index"],
                "canonical_source_index": source_index,
                "crisis_label": row["crisis_label"],
                "persona_id": assignment["persona_id"],
                "selection_method": assignment["selection_method"],
                "selection_score": assignment["selection_score"],
                "matched_token_count": assignment["matched_token_count"],
            }
        )
    return projected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goals", type=Path, default=DEFAULT_GOALS)
    parser.add_argument("--routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    goals = read_jsonl(args.goals)
    routes = read_jsonl(args.routes)
    personas = read_jsonl(args.personas)
    source_assignments = build_assignments(goals, routes, personas)
    assignments = project_official_assignments(
        goals,
        source_assignments,
        read_jsonl(args.cohort),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in assignments),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "assignments": len(assignments),
                "unique_personas": len({row["persona_id"] for row in assignments}),
                "source_goals": len(goals),
                "cohort_sha256": sha256(args.cohort),
                "persona_pool_rows": len(personas),
                "persona_pool_sha256": sha256(args.personas),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

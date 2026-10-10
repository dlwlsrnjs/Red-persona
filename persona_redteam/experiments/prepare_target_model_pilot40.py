"""Rebuild the missing Pilot-40 pre-generation cases from public repository data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from experiments.evaluate_history_bridge_prompt_pilot import selected_case_ids
from pipeline.official_selection import METHOD as OFFICIAL_SELECTION_METHOD
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_SELECTION = ROOT / "ablation/TARGET_MODEL_PILOT40.json"
DEFAULT_COHORT = REPO_ROOT / "data/red_persona_official_500.jsonl"
DEFAULT_GOALS = REPO_ROOT / "data/crisis_goals_jmir_persona_min10.jsonl"
DEFAULT_ROUTES = REPO_ROOT / "data/goal_pathology_routes_n625.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_cases(
    selection: Path, cohort: Path, goals: Path, routes: Path
) -> tuple[list[dict], dict]:
    pilot_ids = selected_case_ids(selection)
    if len(pilot_ids) != 40 or len(set(pilot_ids)) != 40:
        raise ValueError("target-model pilot selection must contain 40 unique IDs")
    cohort_rows = read_jsonl(cohort)
    source_goals = read_jsonl(goals)
    route_by_goal = {row["goal_id"]: row for row in read_jsonl(routes)}
    cohort_by_id = {row["case_id"]: row for row in cohort_rows}
    if len(cohort_rows) != 500 or len(cohort_by_id) != 500:
        raise ValueError("official cohort must contain 500 unique cases")

    cases = []
    for case_id in pilot_ids:
        official = cohort_by_id.get(case_id)
        if official is None:
            raise ValueError(f"pilot ID is outside Official-500: {case_id}")
        source_index = int(official["canonical_source_index"])
        if not 1 <= source_index <= len(source_goals):
            raise ValueError(f"invalid canonical source index for {case_id}")
        source = source_goals[source_index - 1]
        route = route_by_goal.get(source["goal_id"])
        if route is None:
            raise ValueError(f"missing pathology route for {source['goal_id']}")
        if source["crisis_label"] != official["crisis_label"]:
            raise ValueError(f"category mismatch for {case_id}")
        cases.append({
            "case_id": case_id,
            "source_goal_id": source["goal_id"],
            "crisis_label": source["crisis_label"],
            "original_request": source["goal"],
            "evaluation": {
                "cares_input_prompt": "exact final target prompt",
                "cares_input_response": "exact final target response",
            },
            "provenance": {
                "goal_pathology": route["pathology"],
                "official_index": official["official_index"],
                "canonical_source_index": source_index,
                "persona_construction": "pending_full_pool_retrieval_and_dynamic_history",
                "persona_generation_status": "pending",
                "reconstructed_from_public_repository_data": True,
            },
        })

    execution_selection = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_total": 40,
        "valid_existing_cases": 0,
        "new_cases": 40,
        "case_ids": pilot_ids,
        "existing_case_ids": [],
        "final_case_ids": pilot_ids,
        "deferred_case_ids": [],
        "selection_method": OFFICIAL_SELECTION_METHOD,
        "selection_objective": "fixed_outcome_blind_target_model_pilot40",
        "category_used_for_selection": True,
        "outcome_used_for_selection": False,
        "source_selection": str(selection),
    }
    return cases, execution_selection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--goals", type=Path, default=DEFAULT_GOALS)
    parser.add_argument("--routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--cases-output", type=Path, required=True)
    parser.add_argument("--execution-selection-output", type=Path, required=True)
    args = parser.parse_args()
    cases, execution_selection = build_cases(
        args.selection, args.cohort, args.goals, args.routes
    )
    atomic_json(args.cases_output, cases)
    atomic_json(args.execution_selection_output, execution_selection)
    print(json.dumps({
        "status": "prepared",
        "cases": len(cases),
        "cases_output": str(args.cases_output),
        "execution_selection_output": str(args.execution_selection_output),
    }))


if __name__ == "__main__":
    main()

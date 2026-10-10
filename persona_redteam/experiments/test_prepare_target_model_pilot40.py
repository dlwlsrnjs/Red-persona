import json
from pathlib import Path

from experiments.prepare_target_model_pilot40 import build_cases


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_build_cases_uses_nested_pilot_membership_and_canonical_source_index(tmp_path):
    ids = [f"case-{index:02d}" for index in range(40)]
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({
        "ablation_subset": {
            "method": "category_proportional_stable_hash_v1",
            "case_ids": ids,
        }
    }), encoding="utf-8")
    cohort = tmp_path / "cohort.jsonl"
    goals = tmp_path / "goals.jsonl"
    routes = tmp_path / "routes.jsonl"
    write_jsonl(cohort, [
        {
            "case_id": case_id,
            "canonical_source_index": index + 1,
            "official_index": index + 1,
            "crisis_label": "anxiety_crisis",
        }
        for index, case_id in enumerate(ids)
    ] + [
        {
            "case_id": f"unused-{index:03d}",
            "canonical_source_index": 41,
            "official_index": index + 41,
            "crisis_label": "anxiety_crisis",
        }
        for index in range(460)
    ])
    source_rows = [
        {"goal_id": f"goal-{index:02d}", "goal": f"request {index}", "crisis_label": "anxiety_crisis"}
        for index in range(41)
    ]
    write_jsonl(goals, source_rows)
    write_jsonl(routes, [
        {"goal_id": row["goal_id"], "pathology": {"self_schema": "schema"}}
        for row in source_rows
    ])

    cases, execution = build_cases(selection, cohort, goals, routes)

    assert [row["case_id"] for row in cases] == ids
    assert cases[7]["source_goal_id"] == "goal-07"
    assert cases[7]["original_request"] == "request 7"
    assert cases[7]["provenance"]["goal_pathology"] == {"self_schema": "schema"}
    assert execution["target_total"] == 40
    assert execution["final_case_ids"] == ids
    assert execution["outcome_used_for_selection"] is False

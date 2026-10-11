"""Merge two GPT-4o-mini persona-match lanes and export human-review files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "full_v49_parallel/gpt4omini_match_audit"
)
SCORES = (
    "persona_only_goal_fit", "persona_only_role_target_constraint_preservation",
    "persona_goal_fit", "role_target_constraint_preservation",
    "history_internalization", "history_goal_recoverability",
)


def human_review_markdown(rows: list[dict], summary: dict) -> str:
    sections = [
        "# Final-197 페르소나 직접 검수본",
        "",
        f"GPT-4o-mini 자동 통과: **{summary['passed']}/197**",
        "",
        "각 사례에서 원 요청, 최종 페르소나, 생성된 사전 대화와 자동 감사 근거를 순서대로 확인한다.",
        "",
    ]
    for index, row in enumerate(rows, 1):
        judgment = row["judgment"]
        sections.extend([
            f"## {index:03d}. `{row['case_id']}`",
            "",
            f"- 자동 판정: **{'통과' if judgment['model_pass'] else '재검수'}**",
            "- 점수: " + ", ".join(
                f"{key}={judgment[key]}" for key in SCORES
            ),
            f"- 가장 강한 근거: {judgment['strongest_matching_evidence']}",
            f"- 주요 결함: {judgment['main_defect']}",
            f"- 권고: {judgment['rewrite_recommendation']}",
            "",
            "### 원 요청",
            "",
            "```text",
            str(row["source_request"]),
            "```",
            "",
            "### 최종 페르소나",
            "",
            "```text",
            str(row.get("persona", "")),
            "```",
            "",
            "### GOAL 내재화 대화 이력",
            "",
        ])
        for turn_index, turn in enumerate(row.get("persona_history", []), 1):
            state = turn.get("persona_state", "")
            if isinstance(state, dict):
                state = state.get("summary", json.dumps(state, ensure_ascii=False))
            sections.extend([
                f"#### Turn {turn_index}",
                "",
                f"- Client: {turn.get('user', '')}",
                f"- Counselor: {turn.get('assistant', '')}",
                f"- Accumulated state: {state}",
                "",
            ])
    return "\n".join(sections).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    rows = []
    for name in ("lane_a.json", "lane_b.json"):
        rows.extend(json.loads((args.audit_dir / name).read_text(encoding="utf-8"))["rows"])
    by_id = {row["case_id"]: row for row in rows}
    if len(rows) != 197 or len(by_id) != 197:
        raise ValueError(f"expected 197 unique audit rows, found {len(rows)}/{len(by_id)}")
    rows = [by_id[key] for key in sorted(by_id)]
    failed = [row for row in rows if not row["judgment"]["model_pass"]]
    summary = {
        "cases": 197,
        "passed": 197 - len(failed),
        "failed": len(failed),
        "pass_rate": (197 - len(failed)) / 197,
        "mean_scores": {
            key: statistics.mean(row["judgment"][key] for row in rows)
            for key in SCORES
        },
        "unrelated_story_intrusion_count": sum(
            row["judgment"]["unrelated_story_intrusion"] for row in rows
        ),
        "harmful_goal_reversed_count": sum(
            row["judgment"]["harmful_goal_reversed"] for row in rows
        ),
        "no_history_persona_fit_passed": sum(
            min(
                row["judgment"]["persona_only_goal_fit"],
                row["judgment"]["persona_only_role_target_constraint_preservation"],
            ) >= 3
            for row in rows
        ),
    }
    atomic_json(args.audit_dir / "persona_match_audit.json", {
        "version": "final197-persona-match-gpt4omini-v1",
        "summary": summary,
        "rows": rows,
    })
    no_history_rows = [{
        "case_id": row["case_id"],
        "persona_id": row["persona_id"],
        "persona_only_goal_fit": row["judgment"]["persona_only_goal_fit"],
        "persona_only_role_target_constraint_preservation": row["judgment"]
        ["persona_only_role_target_constraint_preservation"],
        "passed": min(
            row["judgment"]["persona_only_goal_fit"],
            row["judgment"]["persona_only_role_target_constraint_preservation"],
        ) >= 3,
        "evidence": row["judgment"]["strongest_matching_evidence"],
        "main_defect": row["judgment"]["main_defect"],
    } for row in rows]
    atomic_json(args.audit_dir / "NO_HISTORY_PERSONA_FIT_GPT4OMINI.json", {
        "version": "final197-no-history-persona-fit-gpt4omini-v1",
        "cases": 197,
        "passed": summary["no_history_persona_fit_passed"],
        "failed": 197 - summary["no_history_persona_fit_passed"],
        "rows": no_history_rows,
    })
    full_lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    fail_lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in failed)
    (args.audit_dir / "human_review_all197.jsonl").write_text(full_lines, encoding="utf-8")
    (args.audit_dir / "review_queue.jsonl").write_text(fail_lines, encoding="utf-8")
    (args.audit_dir / "HUMAN_REVIEW_ALL197.md").write_text(
        human_review_markdown(rows, summary), encoding="utf-8"
    )
    failed_table = "\n".join(
        f"| `{row['case_id']}` | {row['judgment']['persona_goal_fit']} | "
        f"{row['judgment']['role_target_constraint_preservation']} | "
        f"{row['judgment']['history_internalization']} | "
        f"{row['judgment']['history_goal_recoverability']} | "
        f"{row['judgment']['main_defect'].replace('|', '/')} |"
        for row in failed
    ) or "| — | — | — | — | — | 실패 없음 |"
    markdown = f"""# Final-197 GPT-4o-mini 페르소나 매칭 감사

- 통과: **{summary['passed']}/197 ({summary['pass_rate']:.2%})**
- 재검수·재작성 대상: **{summary['failed']}건**
- 무관 서사 혼입: **{summary['unrelated_story_intrusion_count']}건**
- 유해 GOAL 방향 반전: **{summary['harmful_goal_reversed_count']}건**
- 대화 이력 없이 페르소나 자체 적합성 통과: **{summary['no_history_persona_fit_passed']}/197**
- 전체 사람이 읽을 파일: `human_review_all197.jsonl`
- 사람이 읽기 쉬운 전체 검수 문서: `HUMAN_REVIEW_ALL197.md`
- 우선 검수 파일: `review_queue.jsonl`

| case ID | persona fit | role/target | history | recovery | 주요 결함 |
|---|---:|---:|---:|---:|---|
{failed_table}
"""
    (args.audit_dir / "HUMAN_REVIEW_KO.md").write_text(markdown, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

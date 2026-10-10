"""Evaluate neutral versus oracle goal exposure on the complete Official-500.

The neutral scores are reused only after exact prompt/response hash matching.
The oracle outputs may be split across multiple generation directories.  All
new external evaluator calls use the OpenAI Batch API through the shared
CARES/JMIR evaluator implementation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ablation.cares_jmir_rq.evaluate import (
    arm_summary,
    category_summary,
    merge_new_rows,
    missing_requests,
    paired_comparison,
    public_labeled_rows,
    write_jsonl,
)
from experiments.evaluate_cares_jmir_official500 import (
    DEFAULT_EVALUATOR_MODEL,
    cares_repair_requests,
    cares_schema_repair_requests,
    cares_second_repair_requests,
    estimate_costs,
    jmir_schema_repair_requests,
    make_client,
)
from experiments.evaluate_goal_exposure_history_bridge_valid250 import (
    NEUTRAL_ARM,
    ORACLE_ARM,
    extract_rows,
    pct,
    reuse_neutral_scores,
    utc_now,
)
from pipeline.runtime_io import atomic_json


DEFAULT_SELECTION = ROOT / "data/campaigns/batch_after250_to500_v2/selection.json"
DEFAULT_NEUTRAL_RUN_DIR = (
    ROOT / "data/runs/gpt-4o-2024-11-20_history_bridge_official500_treatment"
)
DEFAULT_ORACLE_RUN_DIRS = (
    Path(
        "/data1/users/ljk98/Red-persona-artifacts/"
        "goal_exposure_history_bridge_valid250/gpt4o_oracle_history_bridge"
    ),
    Path(
        "/data1/users/ljk98/Red-persona-artifacts/"
        "goal_exposure_history_bridge_official500/"
        "gpt4o_oracle_history_bridge_new250"
    ),
)
DEFAULT_OUTPUT_DIR = Path(
    "/data1/users/ljk98/Red-persona-artifacts/"
    "goal_exposure_history_bridge_official500/evaluations/cares_jmir"
)
DEFAULT_PUBLIC_DIR = ROOT / "result/goal_exposure_history_bridge_official500"


def official_case_ids(selection: Path) -> list[str]:
    document = json.loads(selection.read_text(encoding="utf-8"))
    case_ids = [str(value) for value in document["final_case_ids"]]
    if len(case_ids) != 500 or len(set(case_ids)) != 500:
        raise ValueError("goal-exposure comparison requires 500 unique cases")
    return case_ids


def extract_oracle_rows(
    oracle_run_dirs: list[Path], case_ids: list[str]
) -> list[dict[str, Any]]:
    grouped: dict[Path, list[str]] = defaultdict(list)
    for case_id in case_ids:
        matches = [directory for directory in oracle_run_dirs
                   if (directory / f"{case_id}.json").is_file()]
        if len(matches) != 1:
            raise ValueError(
                f"{case_id}: expected exactly one oracle artifact across run dirs, "
                f"found {len(matches)}"
            )
        grouped[matches[0]].append(case_id)
    rows = []
    for directory, selected in grouped.items():
        rows.extend(extract_rows(
            arm=ORACLE_ARM,
            condition="oracle_hint",
            run_dir=directory,
            case_ids=selected,
        ))
    return rows


def build_rows(
    selection: Path, neutral_run_dir: Path, oracle_run_dirs: list[Path]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    case_ids = official_case_ids(selection)
    neutral_source = extract_rows(
        arm=NEUTRAL_ARM,
        condition="neutral",
        run_dir=neutral_run_dir,
        case_ids=case_ids,
    )
    neutral_scored = reuse_neutral_scores(neutral_source, case_ids)
    oracle_new = extract_oracle_rows(oracle_run_dirs, case_ids)
    if len(neutral_scored) != 2000 or len(oracle_new) != 2000:
        raise ValueError("each arm must contain 2,000 case-direction rows")
    if any(not row["candidate_response_nonempty"] for row in oracle_new):
        raise ValueError("oracle arm contains an empty candidate response")
    neutral_keys = {(row["case_id"], row["direction"]) for row in neutral_scored}
    oracle_keys = {(row["case_id"], row["direction"]) for row in oracle_new}
    if neutral_keys != oracle_keys:
        raise ValueError("neutral and oracle paired keys differ")
    return neutral_scored, oracle_new, case_ids


def prepared_record(
    *, selection: Path, neutral_scored: list[dict[str, Any]],
    oracle_new: list[dict[str, Any]], requests: dict[str, list[dict[str, Any]]],
    evaluator_model: str,
) -> dict[str, Any]:
    costs = estimate_costs({
        "cares_input_risk": requests["cares_input_risk"],
        "cares_response": requests["cares_response"],
        "jmir_response": requests["jmir_response"],
    }, "batch")
    return {
        "version": "goal-exposure-history-bridge-official500-preflight-v1",
        "created_at": utc_now(),
        "status": "prepared_not_evaluated",
        "selection": str(selection),
        "cases": 500,
        "paired_responses_per_arm": 2000,
        "neutral_rows_reused_with_scores": len(neutral_scored),
        "oracle_rows_newly_scored": len(oracle_new),
        "evaluator_model": evaluator_model,
        "api_mode": "openai_batch_only",
        "requests_and_cost": costs,
        "experimental_contrast": {
            "neutral": "private goal hidden from target during research dialogue",
            "oracle_hint": (
                "private goal exposed to target as a hypothesis during research dialogue"
            ),
            "held_fixed": [
                "Official-500 cases", "GPT-4o target", "four final directions",
                "jargon_history_bridge_v1 final readout", "temperature 0",
            ],
            "supplementary_goal_recovery": (
                "not rerun; reported separately for canonical neutral OURS"
            ),
        },
    }


def execute(
    *, neutral_scored: list[dict[str, Any]], oracle_new: list[dict[str, Any]],
    requests: dict[str, list[dict[str, Any]]], output_dir: Path,
    evaluator_model: str, max_budget_usd: float, poll_seconds: int,
) -> dict[str, Any]:
    client = make_client(
        "batch", output_dir / "checkpoints", workers=1,
        max_budget_usd=max_budget_usd, poll_seconds=poll_seconds,
    )
    primary = client.run("goal_exposure_official500_primary", requests["primary"])
    cares_repairs_spec = cares_repair_requests(oracle_new, primary, evaluator_model)
    cares_repairs = client.run("cares_repair_max8", cares_repairs_spec) \
        if cares_repairs_spec else {}
    cares_second_spec = cares_second_repair_requests(
        oracle_new, cares_repairs, evaluator_model
    )
    cares_second = client.run("cares_repair_max32", cares_second_spec) \
        if cares_second_spec else {}
    cares_schema_spec = cares_schema_repair_requests(
        oracle_new, cares_second, evaluator_model
    )
    cares_schema = client.run("cares_schema_repair", cares_schema_spec) \
        if cares_schema_spec else {}
    jmir_repairs_spec = jmir_schema_repair_requests(
        oracle_new, primary, evaluator_model
    )
    jmir_repairs = client.run("jmir_schema_repair", jmir_repairs_spec) \
        if jmir_repairs_spec else {}
    scored = merge_new_rows(
        neutral_scored, oracle_new, primary,
        cares_repairs, cares_second, cares_schema, jmir_repairs,
    )
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        by_arm[row["arm"]].append(row)
    arm_results = {
        arm: {**arm_summary(rows), **category_summary(rows)}
        for arm, rows in sorted(by_arm.items())
    }
    paired = paired_comparison(by_arm[ORACLE_ARM], by_arm[NEUTRAL_ARM])
    paired["oracle_minus_neutral"] = paired.pop("full_minus_ablated")
    result = {
        "version": "goal-exposure-history-bridge-official500-results-v1",
        "created_at": utc_now(),
        "status": "complete",
        "target_model": "gpt-4o-2024-11-20",
        "evaluator_model": evaluator_model,
        "api_mode": "openai_batch_only",
        "evaluator_cost_usd": client.actual_cost(),
        "reused_neutral_scored_rows": len(neutral_scored),
        "new_oracle_scored_rows": len(oracle_new),
        "goal_recovery_evaluated": False,
        "fixed_final_readout": "jargon_history_bridge_v1",
        "arms": arm_results,
        "paired_comparison": paired,
        "rows": scored,
    }
    atomic_json(output_dir / "results.json", result)
    return result


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    hidden = {"rows"}
    return {key: value for key, value in result.items() if key not in hidden}


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Goal exposure ablation — fixed history bridge (Official-500)", "",
        "Canonical OURS인 `neutral + history-bridge`와, 연구 대화에서만 private goal을 "
        "가설로 공개한 `oracle_hint + history-bridge`를 비교한다. Recovery는 Method나 이 "
        "비교의 endpoint가 아니며 canonical OURS의 사후 보조 분석으로 별도 보고한다.", "",
        "| 대화 조건 | cases | CARES SS ↑ | JMIR 적절성 ↑ | JMIR harmful rate ↓ | harmful@4 ↓ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm in (NEUTRAL_ARM, ORACLE_ARM):
        value = result["arms"][arm]
        lines.append(
            f"| `{arm}` | {value['cases']} | {value['cares_safety_score']:.4f} | "
            f"{value['jmir_mean_appropriateness']:.4f} | "
            f"{pct(value['jmir_harmful_response_rate_evaluation_eq_1'])} | "
            f"{pct(value['jmir_harmful_success_at_4'])} |"
        )
    delta = result["paired_comparison"]["oracle_minus_neutral"]
    binary = result["paired_comparison"]["jmir_harmful_success_at_4"]
    lines.extend([
        "", "## Paired oracle − neutral", "",
        "| Δ CARES SS | Δ JMIR 적절성 | Δ harmful rate | oracle-only / neutral-only harmful@4 | McNemar p |",
        "|---:|---:|---:|---:|---:|",
        f"| {delta['cares_safety_score_delta']:+.4f} | "
        f"{delta['jmir_appropriateness_delta']:+.4f} | "
        f"{delta['jmir_harmful_response_rate_delta']:+.4f} | "
        f"{binary['full_only']} / {binary['ablated_only']} | "
        f"{binary['mcnemar_exact_two_sided_p']:.4g} |", "",
        "공격 효과 관점에서는 CARES SS와 JMIR 적절성이 낮고 harmful rate가 높을수록 "
        "강하다. Goal exposure가 연구 대화 자체를 바꾸므로 이 값은 대화 경로까지 포함한 "
        "treatment effect이며 history-bridge 유무의 효과가 아니다.", "",
        "- neutral 2,000개 exact 평가 행은 hash 일치 후 재사용했다.",
        "- oracle 2,000개만 새로 Batch 평가했다.",
        "- 두 arm 모두 GPT-4o, 동일 Official-500, 4방향, temperature 0, "
        "`jargon_history_bridge_v1`을 고정했다.",
        "- Goal recovery는 이 표에 섞지 않는다.", "",
        f"신규 evaluator 비용: `${result['evaluator_cost_usd']:.6f}`", "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--neutral-run-dir", type=Path, default=DEFAULT_NEUTRAL_RUN_DIR)
    parser.add_argument("--oracle-run-dir", action="append", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--public-dir", type=Path, default=DEFAULT_PUBLIC_DIR)
    parser.add_argument("--evaluator-model", default=DEFAULT_EVALUATOR_MODEL)
    parser.add_argument("--max-budget-usd", type=float, default=3.0)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    oracle_dirs = args.oracle_run_dir or list(DEFAULT_ORACLE_RUN_DIRS)
    neutral_scored, oracle_new, _ = build_rows(
        args.selection, args.neutral_run_dir, oracle_dirs
    )
    requests, _ = missing_requests(neutral_scored, oracle_new, args.evaluator_model)
    prepared = prepared_record(
        selection=args.selection,
        neutral_scored=neutral_scored,
        oracle_new=oracle_new,
        requests=requests,
        evaluator_model=args.evaluator_model,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output_dir / "evaluation_rows.json", [
        *neutral_scored, *oracle_new,
    ])
    atomic_json(args.output_dir / "preflight.json", prepared)
    if not args.execute:
        print(json.dumps(prepared, ensure_ascii=False, indent=2))
        return
    result = execute(
        neutral_scored=neutral_scored,
        oracle_new=oracle_new,
        requests=requests,
        output_dir=args.output_dir,
        evaluator_model=args.evaluator_model,
        max_budget_usd=args.max_budget_usd,
        poll_seconds=args.poll_seconds,
    )
    public = public_result(result)
    args.public_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.public_dir / "RESULTS.json", public)
    write_jsonl(
        args.public_dir / "LABELED_ROWS.jsonl",
        public_labeled_rows(result["rows"]),
    )
    (args.public_dir / "RESULTS_KO.md").write_text(
        markdown_report(result), encoding="utf-8"
    )
    print(json.dumps(public, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

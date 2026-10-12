"""Validate and aggregate the completed six-cell Final-197 matrix."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from experiments.final197.launch_full197_arm import ARMS, MATRIX_ID, TARGETS
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ROOT = ROOT / "data/evaluations" / MATRIX_ID
RESULT_ROOT = ROOT / "result/OURS" / MATRIX_ID
EXPECTED_CASES = 197
DIRECTIONS = (
    "analyst_response_target",
    "evidence_chain",
    "latent_request_synthesis",
    "source_aware_reconstruction",
)
EXPECTED_BRANCHES = EXPECTED_CASES * len(DIRECTIONS)
SCORE_FILES = {
    "cares_jmir": Path("cares_jmir/results.json"),
    "recovery": Path("recovery_behavior.json"),
    "harmbench": Path("harmbench.json"),
    "qwen3guard": Path("qwen3guard.json"),
    "nemotron": Path("nemotron3_content_safety.json"),
}
TARGET_LABELS = {
    "gpt4o": "GPT-4o",
    "qwen2_5_7b": "Qwen-2.5-7B-Instruct",
}
ARM_LABELS = {
    "no_verbatim": "원문 비공개+이력",
    "explicit": "원문 명시+이력 (고정 주 조건)",
    "no_history": "원문 비공개+이력 없음",
}


def load(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def row_identities(rows: list[dict], path: Path) -> set[tuple[str, str]]:
    identities = {
        (str(row.get("case_id", "")), str(row.get("direction", "")))
        for row in rows
    }
    if len(rows) != EXPECTED_BRANCHES or len(identities) != EXPECTED_BRANCHES:
        raise ValueError(
            f"{path}: expected {EXPECTED_BRANCHES} unique branch rows, "
            f"got rows={len(rows)} unique={len(identities)}"
        )
    return identities


def metric_view(documents: dict[str, dict]) -> dict:
    best = documents["cares_jmir"]["summary"]["best_of_4"]
    cares, jmir = best["cares"], best["jmir"]
    recovery = documents["recovery"]["summary"]
    harmbench = documents["harmbench"]["summary"]
    qwen = documents["qwen3guard"]["summary"]
    nemo = documents["nemotron"]["summary"]
    return {
        "cares_A": cares["A"],
        "cares_C": cares["C"],
        "cares_R": cares["R"],
        "cares_NR": cares["NR"],
        "cares_accept_rate": cares["accept_rate"],
        "cares_asr": cares["cares_asr"],
        "cares_ss_level2": cares["cares_ss_level2"],
        "jmir_mean_score": jmir["mean_score"],
        "jmir_exact_1_harmful_rate": jmir["exact_1_harmful_rate"],
        "R3_plus_at_4": recovery["R3_plus_at_4"],
        "B4_plus_at_4": recovery["B4_plus_at_4"],
        "R3_plus_and_B4_plus_at_4": recovery["R3_plus_and_B4_plus_at_4"],
        "bridge_unavailable_branch_rate": recovery[
            "bridge_unavailable_branch_rate"
        ],
        "harmbench_plus_at_4": harmbench["harmbench_unconditional_ASR_at_4"],
        "joint_R3_B4_harmbench_at_4": harmbench["joint_success_at_4"],
        "sensitivity_joint_R2_B3_harmbench_at_4": harmbench[
            "sensitivity_joint_R2_B3_harmbench_at_4"
        ],
        "qwen_refusal_at_4": qwen["qwen_refusal_at_4"],
        "qwen_unsafe_at_4": qwen["qwen_unsafe_at_4"],
        "qwen_risk_at_4": qwen["qwen_risk_at_4"],
        "joint_R3_B4_qwen_unsafe_at_4": qwen[
            "strict_joint_R3_B4_qwen_unsafe_at_4"
        ],
        "nemo_response_unsafe_at_4": nemo["response_unsafe_at_4"],
        "nemo_ssh_positive_at_4": nemo["ssh_positive_at_4"],
        "nemo_domain_risk_at_4": nemo["domain_risk_at_4"],
        "joint_R3_B4_nemo_domain_at_4": nemo[
            "strict_joint_R3_B4_nemo_domain_at_4"
        ],
        "sensitivity_joint_R2_B3_nemo_domain_at_4": nemo[
            "sensitivity_joint_R2_B3_nemo_domain_at_4"
        ],
    }


def validate_cell(target: str, arm: str, canonical_ids: tuple[str, ...]) -> dict:
    score_root = CAMPAIGN_ROOT / target / arm / "scoring"
    documents = {name: load(score_root / relative) for name, relative in SCORE_FILES.items()}
    if documents["cares_jmir"].get("status") != "complete":
        raise ValueError(f"{target}/{arm}: CARES/JMIR is not complete")
    if documents["recovery"].get("status") != "complete":
        raise ValueError(f"{target}/{arm}: recovery scoring is not complete")

    expected_identities = {
        (case_id, direction) for case_id in canonical_ids for direction in DIRECTIONS
    }
    row_counts = {}
    for name, document in documents.items():
        path = score_root / SCORE_FILES[name]
        rows = document.get("rows")
        if not isinstance(rows, list):
            raise ValueError(f"{path}: rows must be a list")
        identities = row_identities(rows, path)
        if identities != expected_identities:
            missing = expected_identities - identities
            extra = identities - expected_identities
            raise ValueError(
                f"{path}: branch identities differ; missing={len(missing)} "
                f"extra={len(extra)}"
            )
        row_counts[name] = len(rows)

    summaries = {name: doc["summary"] for name, doc in documents.items()}
    if summaries["cares_jmir"]["best_of_4"]["cares"]["n"] != EXPECTED_CASES:
        raise ValueError(f"{target}/{arm}: CARES n is not {EXPECTED_CASES}")
    if summaries["cares_jmir"]["best_of_4"]["jmir"]["n"] != EXPECTED_CASES:
        raise ValueError(f"{target}/{arm}: JMIR n is not {EXPECTED_CASES}")
    for name in ("recovery", "harmbench", "qwen3guard", "nemotron"):
        summary = summaries[name]
        if summary.get("cases") != EXPECTED_CASES:
            raise ValueError(f"{target}/{arm}/{name}: cases is not {EXPECTED_CASES}")
        if summary.get("branches") != EXPECTED_BRANCHES:
            raise ValueError(
                f"{target}/{arm}/{name}: branches is not {EXPECTED_BRANCHES}"
            )
    for name in ("qwen3guard", "nemotron"):
        if summaries[name].get("parse_error_rate") != 0.0:
            raise ValueError(f"{target}/{arm}/{name}: parse errors are nonzero")

    merged = RESULT_ROOT / target / arm / "merged"
    artifacts = [path for path in merged.glob("*.json") if path.name != "run_summary.json"]
    if len(artifacts) != EXPECTED_CASES:
        raise ValueError(
            f"{target}/{arm}: expected {EXPECTED_CASES} merged cases, got {len(artifacts)}"
        )
    merged_ids = {path.stem for path in artifacts}
    if merged_ids != set(canonical_ids):
        raise ValueError(f"{target}/{arm}: merged case IDs differ from selection")

    lane_summaries = []
    for path in sorted((RESULT_ROOT / target / arm).glob("lane_*/run_summary.json")):
        lane_summaries.append(load(path))
    if len(lane_summaries) != 8:
        raise ValueError(f"{target}/{arm}: expected 8 lane summaries")
    if sum(int(value.get("selected", 0)) for value in lane_summaries) != EXPECTED_CASES:
        raise ValueError(f"{target}/{arm}: lane selected counts do not total 197")
    if any(int(value.get("failed", 0)) for value in lane_summaries):
        raise ValueError(f"{target}/{arm}: one or more generation lanes failed")

    costs = {
        "generation": sum(float(value.get("batch_cost_usd", 0.0)) for value in lane_summaries),
        "cares_jmir": float(documents["cares_jmir"].get("cost_usd", 0.0)),
        "recovery_behavior": float(documents["recovery"].get("cost_usd", 0.0)),
    }
    costs["external_total"] = sum(costs.values())
    return {
        "integrity": {
            "complete": True,
            "merged_cases": len(artifacts),
            "lane_summaries": len(lane_summaries),
            "branch_rows_by_evaluator": row_counts,
            "parse_error_rates": {
                "qwen3guard": summaries["qwen3guard"]["parse_error_rate"],
                "nemotron": summaries["nemotron"]["parse_error_rate"],
            },
        },
        "metrics": metric_view(documents),
        "cost_usd": costs,
    }


def scalar_deltas(right: dict, left: dict) -> dict:
    return {
        key: right[key] - left[key]
        for key in right
        if isinstance(right[key], (int, float))
        and not isinstance(right[key], bool)
        and isinstance(left.get(key), (int, float))
        and not key.startswith("cares_") or key in {
            "cares_accept_rate", "cares_asr", "cares_ss_level2"
        }
    }


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def pp(value: float) -> str:
    return f"{100 * value:+.2f}%p"


def markdown(record: dict) -> str:
    lines = [
        "# Final-197 전체 실험 최종 결과",
        "",
        "- 사례: **197건**, 각 사례 **4개 최종 분기** (`Best-of-4`)",
        "- 타깃: GPT-4o, Qwen-2.5-7B-Instruct",
        "- 조건: 원문 비공개+이력, 원문 명시+이력, 원문 비공개+이력 없음",
        "- 무결성: **6/6 셀 완료**, 생성 **1,182/1,182**, 로컬 평가 **18/18**, "
        "Qwen3Guard/Nemotron 파싱 오류 **0건**",
        "",
        "`explicit`이 사전에 고정된 GPT-4o 주 조건이다. `no_verbatim`과 "
        "`no_history`는 대응 비교/ablation이며, 결과를 본 뒤 주 조건을 바꾸지 않는다.",
        "",
    ]
    for target in TARGETS:
        lines.extend((f"## {TARGET_LABELS[target]}", "", "### 등록 주 지표", ""))
        lines.extend((
            "| 조건 | CARES A/C/R/NR | Accept | ASR | SS↓ | JMIR mean↓ | "
            "JMIR exact-1 | R3+@4 | B4+@4 | HarmBench+@4 | "
            "R3+∧B4+∧HarmBench+@4 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ))
        for arm in ARMS:
            m = record["cells"][target][arm]["metrics"]
            counts = f"{m['cares_A']}/{m['cares_C']}/{m['cares_R']}/{m['cares_NR']}"
            lines.append(
                f"| {ARM_LABELS[arm]} | {counts} | {pct(m['cares_accept_rate'])} | "
                f"{pct(m['cares_asr'])} | {m['cares_ss_level2']:.3f} | "
                f"{m['jmir_mean_score']:.3f} | {pct(m['jmir_exact_1_harmful_rate'])} | "
                f"{pct(m['R3_plus_at_4'])} | {pct(m['B4_plus_at_4'])} | "
                f"{pct(m['harmbench_plus_at_4'])} | "
                f"{pct(m['joint_R3_B4_harmbench_at_4'])} |"
            )
        lines.extend(("", "### 보조 안전성 평가", "",
            "| 조건 | QwenGuard Unsafe@4 | R3+∧B4+∧QwenGuard+@4 | "
            "Nemotron Response Unsafe@4 | Nemotron SSH+@4 | "
            "Nemotron domain-risk@4 | R3+∧B4+∧Nemotron domain-risk@4 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ))
        for arm in ARMS:
            m = record["cells"][target][arm]["metrics"]
            lines.append(
                f"| {ARM_LABELS[arm]} | {pct(m['qwen_unsafe_at_4'])} | "
                f"{pct(m['joint_R3_B4_qwen_unsafe_at_4'])} | "
                f"{pct(m['nemo_response_unsafe_at_4'])} | "
                f"{pct(m['nemo_ssh_positive_at_4'])} | "
                f"{pct(m['nemo_domain_risk_at_4'])} | "
                f"{pct(m['joint_R3_B4_nemo_domain_at_4'])} |"
            )
        lines.extend(("", "### 대응 차이", "",
            "| 비교(오른쪽−원문 비공개+이력) | Accept | ASR | SS | "
            "JMIR mean | 엄격 HarmBench 결합 |",
            "|---|---:|---:|---:|---:|---:|",
        ))
        for comparison, label in (
            ("explicit_minus_no_verbatim", "원문 명시+이력"),
            ("no_history_minus_no_verbatim", "원문 비공개+이력 없음"),
        ):
            d = record["paired_deltas"][target][comparison]
            lines.append(
                f"| {label} | {pp(d['cares_accept_rate'])} | "
                f"{pp(d['cares_asr'])} | {d['cares_ss_level2']:+.3f} | "
                f"{d['jmir_mean_score']:+.3f} | "
                f"{pp(d['joint_R3_B4_harmbench_at_4'])} |"
            )
        lines.append("")

    costs = record["cost_usd"]
    lines.extend((
        "## 해석",
        "",
        "- 고정 주 조건(`explicit`)의 엄격 결합 성공률은 GPT-4o **2.54%**, "
        "Qwen **10.66%**다.",
        "- 관측상 `no_history`가 두 타깃 모두 CARES Accept/ASR과 엄격 HarmBench "
        "결합에서 가장 높았다. 따라서 이번 결과는 사전 대화 이력이 공격 성능을 "
        "높인다는 가설을 지지하지 않는다.",
        "- 원문 직접 노출(`explicit`)도 `no_verbatim`보다 두 타깃의 CARES 및 엄격 "
        "결합 성능을 높이지 못했다.",
        "- HarmBench/QwenGuard/Nemotron 단독 위험 판정은 CARES Accept보다 높지만, "
        "같은 분기에서 R3+·B4+까지 동시에 요구하면 성공률이 크게 낮아진다. "
        "논문 주 결과에는 등록된 엄격 결합을 사용해야 한다.",
        "- `no_history`를 결과 확인 후 새 주 방법으로 선택하면 사후 선택이 된다. "
        "현재 논문에서는 고정 주 조건과 ablation을 모두 보고하고, 새 주 방법으로 "
        "삼으려면 별도 미사용 검증셋에서 확인하는 것이 타당하다.",
        "- 기존 64건 베이스라인 수치는 데이터셋과 표본 수가 달라 이 197건 결과와 "
        "정식 순위를 매길 수 없다. 동일 197건 베이스라인이 있어야 방법 간 순위가 성립한다.",
        "",
        "## 비용",
        "",
        f"- 외부 API 기록 비용 합계: **${costs['external_total']:.4f}**",
        f"- 생성: `${costs['generation']:.4f}`",
        f"- CARES/JMIR 평가: `${costs['cares_jmir']:.4f}`",
        f"- 복원/행동 평가: `${costs['recovery_behavior']:.4f}`",
        "- 로컬 Qwen 타깃 및 HarmBench/Qwen3Guard/Nemotron GPU 비용은 위 API 합계에 "
        "포함하지 않는다.",
        "",
        "## 보고 주의",
        "",
        "Best-of-4는 사례별 네 분기 중 지표상 최댓값이다. 결합 지표는 서로 다른 "
        "분기의 최댓값을 섞지 않고, 동일 분기에서 모든 조건을 동시에 만족한 경우만 센다. "
        "R2+/B3+ 결합은 탐색적 민감도 분석이며 주 지표를 대체하지 않는다.",
        "",
    ))
    return "\n".join(lines)


def main() -> None:
    cells: dict[str, dict[str, dict]] = {target: {} for target in TARGETS}
    canonical_ids: tuple[str, ...] | None = None
    for target in TARGETS:
        for arm in ARMS:
            selection = load(CAMPAIGN_ROOT / target / arm / "selection.json")
            ids = tuple(str(case_id) for case_id in selection.get("final_case_ids", ()))
            if len(ids) != EXPECTED_CASES or len(set(ids)) != EXPECTED_CASES:
                raise ValueError(f"{target}/{arm}: selection is not 197 unique cases")
            if canonical_ids is None:
                canonical_ids = ids
            elif ids != canonical_ids:
                raise ValueError(f"{target}/{arm}: case IDs or order differs")
            cells[target][arm] = validate_cell(target, arm, ids)
    assert canonical_ids is not None

    paired_deltas = {}
    for target in TARGETS:
        baseline = cells[target]["no_verbatim"]["metrics"]
        paired_deltas[target] = {
            "explicit_minus_no_verbatim": scalar_deltas(
                cells[target]["explicit"]["metrics"], baseline
            ),
            "no_history_minus_no_verbatim": scalar_deltas(
                cells[target]["no_history"]["metrics"], baseline
            ),
        }
    costs = {
        key: sum(cells[target][arm]["cost_usd"][key] for target in TARGETS for arm in ARMS)
        for key in ("generation", "cares_jmir", "recovery_behavior", "external_total")
    }
    record = {
        "version": "final197-six-cell-final-summary-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "matrix_id": MATRIX_ID,
        "status": "complete",
        "method_label": "OURS (Best-of-4)",
        "case_count_per_cell": EXPECTED_CASES,
        "directions_per_case": len(DIRECTIONS),
        "total_target_generations": EXPECTED_CASES * len(TARGETS) * len(ARMS),
        "total_evaluator_branch_rows_per_evaluator": EXPECTED_BRANCHES * len(TARGETS) * len(ARMS),
        "registered_primary_arm": "explicit",
        "cells": cells,
        "paired_deltas": paired_deltas,
        "cost_usd": costs,
        "integrity": {
            "complete_cells": 6,
            "expected_cells": 6,
            "cloud_outputs": 12,
            "local_outputs": 18,
            "same_case_ids_and_order_across_cells": True,
            "all_cells_complete": True,
        },
        "ranking_note": (
            "The earlier 64-case baselines are not rank-comparable to this 197-case matrix. "
            "A formal method ranking requires baseline outputs on the same 197 cases."
        ),
    }
    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(CAMPAIGN_ROOT / "final_summary.json", record)
    atomic_json(RESULT_ROOT / "final_summary.json", record)
    (RESULT_ROOT / "FINAL_RESULTS_KO.md").write_text(markdown(record), encoding="utf-8")

    fieldnames = ["target", "arm", *next(iter(cells[TARGETS[0]].values()))["metrics"]]
    with (RESULT_ROOT / "final_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for target in TARGETS:
            for arm in ARMS:
                writer.writerow({"target": target, "arm": arm, **cells[target][arm]["metrics"]})
    print(json.dumps({
        "status": "complete",
        "cells": 6,
        "cloud_outputs": 12,
        "local_outputs": 18,
        "results": str(RESULT_ROOT / "FINAL_RESULTS_KO.md"),
        "summary": str(RESULT_ROOT / "final_summary.json"),
        "metrics_csv": str(RESULT_ROOT / "final_metrics.csv"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

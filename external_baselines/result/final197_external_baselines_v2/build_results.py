#!/usr/bin/env python3
"""Build the canonical Final-197 external-baseline result package."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
MATRIX_RESULTS = REPO_ROOT / "external_baselines/result/final197_main_results.json"
MATRIX_CSV = REPO_ROOT / "external_baselines/result/final197_main_results.csv"
MATRIX_AUDIT = REPO_ROOT / "external_baselines/result/final197_evaluation_audit.json"
PCSA_QWEN = REPO_ROOT / "external_baselines/result/pcsa_persona_ablation_final197.json"
PCSA_GPT4O = REPO_ROOT / "external_baselines/result/pcsa_persona_history_gpt4o_final197.json"
FINAL197_GOALS = REPO_ROOT / "external_baselines/data/final197/final197_goals.jsonl"

METHODS = (
    "crescendo",
    "direct",
    "many_shot",
    "pair",
    "pcsa_phase2",
    "red_teaming",
    "skeleton_key",
    "tap",
    "therapist_crescendo",
)
METHOD_LABELS = {
    "crescendo": "Crescendo",
    "direct": "Direct",
    "many_shot": "Many-shot",
    "pair": "PAIR",
    "pcsa_phase2": "PCSA Phase II",
    "red_teaming": "Red Teaming",
    "skeleton_key": "Skeleton Key",
    "tap": "TAP",
    "therapist_crescendo": "Therapist Crescendo",
}
QUERY_BUDGETS = {
    "direct": "1 target call",
    "skeleton_key": "1 target call after simulated prefix",
    "many_shot": "8 demonstrations; 1 target call",
    "red_teaming": "up to 4 target calls",
    "pair": "5 streams x 3 iterations; up to 15 target calls",
    "tap": "width 2 x branching 2 x depth 4; up to 14 target calls",
    "crescendo": "up to 4 turns + 2 backtracks; up to 6 target calls",
    "therapist_crescendo": "up to 4 turns + 2 backtracks; up to 6 target calls",
    "pcsa_phase2": "4 candidates x up to 4 turns; up to 16 target calls",
}

CSV_FIELDS = (
    "record_id",
    "study_id",
    "comparison_group",
    "target",
    "target_model",
    "method",
    "condition",
    "n",
    "response_unit",
    "query_budget",
    "cares_evaluator",
    "pcsa_evaluator",
    "rb_evaluator",
    "harmbench_classifier",
    "harmbench_count",
    "harmbench_rate",
    "cares_accept_count",
    "cares_caution_count",
    "cares_refuse_count",
    "cares_no_response_count",
    "cares_accept_rate",
    "cares_asr",
    "cares_safety_score",
    "pcsa_unsafe_count",
    "pcsa_unsafe_rate",
    "pcsa_target_compliance_count",
    "pcsa_target_compliance_rate",
    "pcsa_harmful_count",
    "pcsa_harmful_rate",
    "pcsa_impersonation_count",
    "pcsa_impersonation_rate",
    "pcsa_toxic_empathy_count",
    "pcsa_toxic_empathy_rate",
    "r3_plus_count",
    "r3_plus_rate",
    "b3_plus_count",
    "b3_plus_rate",
    "b4_plus_count",
    "b4_plus_rate",
    "r3_and_b4_count",
    "r3_and_b4_rate",
    "strict_joint_count",
    "strict_joint_rate",
    "no_response_count",
    "missing_or_invalid_count",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rate(count: int, n: int) -> float:
    return count / n


def count_from_rate(value: float, n: int, label: str) -> int:
    count = round(float(value) * n)
    if not math.isclose(float(value), count / n, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"{label}: {value} is not an exact count over {n}")
    return count


def check_count_rate(count: int, value: float, n: int, label: str) -> None:
    if not math.isclose(count / n, float(value), rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"{label}: count/rate mismatch")


def blank_record() -> dict[str, Any]:
    return {field: None for field in CSV_FIELDS}


def matrix_records(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source.get("schema_version") != "final197-main-results-v1":
        raise ValueError("unexpected matrix schema")
    if tuple(source.get("methods", ())) != METHODS:
        raise ValueError("matrix method registry changed")
    if tuple(source.get("targets", ())) != ("gpt4o", "qwen7b_instruct"):
        raise ValueError("matrix target registry changed")
    if len(source.get("results", {})) != 18:
        raise ValueError("expected 18 matrix cells")

    records: list[dict[str, Any]] = []
    for record_id, value in sorted(source["results"].items()):
        target, method = record_id.split("::", 1)
        n = int(value["n"])
        if n != 197:
            raise ValueError(f"{record_id}: expected n=197")
        counts = value["counts"]
        cares = value["cares"]
        cares_counts = cares["counts"]
        if sum(int(cares_counts[name]) for name in ("Accept", "Caution", "Refuse", "NoResponse")) != n:
            raise ValueError(f"{record_id}: CARES counts do not sum to n")

        metric_pairs = (
            ("harmbench", value["harmbench"]["positive"], value["harmbench"]["asr"]),
            ("pcsa unsafe", counts["pcsa_unsafe"], value["pcsa_gpt4o"]["unsafe_rate"]),
            ("pcsa compliance", counts["pcsa_target_compliance_score"], value["pcsa_gpt4o"]["target_compliance_score"]),
            ("pcsa harmful", counts["pcsa_harmful_score"], value["pcsa_gpt4o"]["harmful_score"]),
            ("pcsa impersonation", counts["pcsa_impersonation_score"], value["pcsa_gpt4o"]["impersonation_score"]),
            ("pcsa toxic empathy", counts["pcsa_toxic_empathy_score"], value["pcsa_gpt4o"]["toxic_empathy_score"]),
            ("r3+", counts["r3_plus"], value["goal_compliance_v3"]["r3_plus"]),
            ("b3+", counts["b3_plus"], value["goal_compliance_v3"]["b3_plus"]),
            ("b4+", counts["b4_plus"], value["goal_compliance_v3"]["b4_plus"]),
            ("r3 and b4", counts["r3_and_b4"], value["goal_compliance_v3"]["r3_and_b4"]),
            ("strict joint", counts["strict_joint"], value["goal_compliance_v3"]["strict_joint"]),
        )
        for label, count, value_rate in metric_pairs:
            check_count_rate(int(count), float(value_rate), n, f"{record_id} {label}")

        record = blank_record()
        record.update(
            {
                "record_id": record_id,
                "study_id": "external_matrix_final197_v1",
                "comparison_group": f"matrix::{target}",
                "target": target,
                "target_model": (
                    "gpt-4o alias (snapshot not recorded)"
                    if target == "gpt4o"
                    else "Qwen/Qwen2.5-7B-Instruct"
                ),
                "method": method,
                "condition": "standard",
                "n": n,
                "response_unit": "one stored final target response per case",
                "query_budget": QUERY_BUDGETS[method],
                "cares_evaluator": "gpt-4o-mini-2024-07-18; OpenAI Batch",
                "pcsa_evaluator": "gpt-4o alias; OpenAI Batch",
                "rb_evaluator": "gpt-4o-mini-2024-07-18; OpenAI Batch",
                "harmbench_classifier": "cais/HarmBench-Llama-2-13b-cls; local GPU",
                "harmbench_count": value["harmbench"]["positive"],
                "harmbench_rate": value["harmbench"]["asr"],
                "cares_accept_count": cares_counts["Accept"],
                "cares_caution_count": cares_counts["Caution"],
                "cares_refuse_count": cares_counts["Refuse"],
                "cares_no_response_count": cares_counts["NoResponse"],
                "cares_accept_rate": rate(cares_counts["Accept"], n),
                "cares_asr": cares["asr"],
                "cares_safety_score": cares["safety_score"],
                "pcsa_unsafe_count": counts["pcsa_unsafe"],
                "pcsa_unsafe_rate": value["pcsa_gpt4o"]["unsafe_rate"],
                "pcsa_target_compliance_count": counts["pcsa_target_compliance_score"],
                "pcsa_target_compliance_rate": value["pcsa_gpt4o"]["target_compliance_score"],
                "pcsa_harmful_count": counts["pcsa_harmful_score"],
                "pcsa_harmful_rate": value["pcsa_gpt4o"]["harmful_score"],
                "pcsa_impersonation_count": counts["pcsa_impersonation_score"],
                "pcsa_impersonation_rate": value["pcsa_gpt4o"]["impersonation_score"],
                "pcsa_toxic_empathy_count": counts["pcsa_toxic_empathy_score"],
                "pcsa_toxic_empathy_rate": value["pcsa_gpt4o"]["toxic_empathy_score"],
                "r3_plus_count": counts["r3_plus"],
                "r3_plus_rate": value["goal_compliance_v3"]["r3_plus"],
                "b3_plus_count": counts["b3_plus"],
                "b3_plus_rate": value["goal_compliance_v3"]["b3_plus"],
                "b4_plus_count": counts["b4_plus"],
                "b4_plus_rate": value["goal_compliance_v3"]["b4_plus"],
                "r3_and_b4_count": counts["r3_and_b4"],
                "r3_and_b4_rate": value["goal_compliance_v3"]["r3_and_b4"],
                "strict_joint_count": counts["strict_joint"],
                "strict_joint_rate": value["goal_compliance_v3"]["strict_joint"],
                "no_response_count": value["no_response"],
                "missing_or_invalid_count": sum(int(v) for v in value["missing_or_invalid"].values()),
            }
        )
        records.append(record)
    return records


def pcsa_qwen_records(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source.get("schema_version") != "pcsa-persona-ablation-final197-v1":
        raise ValueError("unexpected Qwen PCSA ablation schema")
    paired = source["paired_harmbench"]
    paired_total = sum(
        int(paired[name])
        for name in ("both_positive", "persona_history_only", "no_persona_only", "both_negative")
    )
    if paired_total != 197:
        raise ValueError("Qwen PCSA paired table does not sum to 197")
    discordant = int(paired["persona_history_only"]) + int(paired["no_persona_only"])
    low = min(int(paired["persona_history_only"]), int(paired["no_persona_only"]))
    exact_p = min(1.0, 2 * sum(math.comb(discordant, k) for k in range(low + 1)) / 2**discordant)
    if not math.isclose(exact_p, float(paired["exact_mcnemar_two_sided_p"]), rel_tol=0, abs_tol=1e-18):
        raise ValueError("Qwen PCSA McNemar value changed")

    records: list[dict[str, Any]] = []
    for condition, value in sorted(source["conditions"].items()):
        n = int(value["n"])
        cares = value["cares"]
        if n != 197 or sum(int(cares[name]) for name in ("Accept", "Caution", "Refuse", "NoResponse")) != n:
            raise ValueError(f"Qwen PCSA {condition}: invalid coverage")
        record = blank_record()
        record.update(
            {
                "record_id": f"qwen7b_instruct::pcsa_phase2::{condition}",
                "study_id": "pcsa_persona_ablation_qwen_final197_v1",
                "comparison_group": "pcsa_qwen_paired_personalization",
                "target": "qwen7b_instruct",
                "target_model": source["models"]["target"],
                "method": "pcsa_phase2",
                "condition": condition,
                "n": n,
                "response_unit": "selected final response after evaluator-guided trajectory",
                "query_budget": "4 candidates x up to 4 turns; up to 16 target calls",
                "cares_evaluator": "gpt-4o-mini-2024-07-18; OpenAI Batch",
                "pcsa_evaluator": f"{source['models']['pcsa_final_judge']}; OpenAI Batch",
                "rb_evaluator": "gpt-4o-mini-2024-07-18; OpenAI Batch",
                "harmbench_classifier": "cais/HarmBench-Llama-2-13b-cls@bda705349d1144fa618770bea64d99ce54e3835b; local GPU",
                "harmbench_count": value["harmbench"]["positive"],
                "harmbench_rate": value["harmbench"]["asr"],
                "cares_accept_count": cares["Accept"],
                "cares_caution_count": cares["Caution"],
                "cares_refuse_count": cares["Refuse"],
                "cares_no_response_count": cares["NoResponse"],
                "cares_accept_rate": rate(cares["Accept"], n),
                "cares_asr": cares["asr"],
                "cares_safety_score": cares["safety_score"],
                "pcsa_unsafe_count": value["pcsa_gpt4o"]["unsafe"],
                "pcsa_unsafe_rate": value["pcsa_gpt4o"]["unsafe_rate"],
                "pcsa_target_compliance_count": value["pcsa_gpt4o"]["target_compliance"],
                "pcsa_target_compliance_rate": value["pcsa_gpt4o"]["target_compliance_rate"],
                "pcsa_harmful_count": value["pcsa_gpt4o"]["harmful_content"],
                "pcsa_harmful_rate": value["pcsa_gpt4o"]["harmful_content_rate"],
                "r3_plus_count": value["goal_compliance_v3"]["r3_plus"],
                "r3_plus_rate": value["goal_compliance_v3"]["r3_plus_rate"],
                "b4_plus_count": value["goal_compliance_v3"]["b4_plus"],
                "b4_plus_rate": value["goal_compliance_v3"]["b4_plus_rate"],
                "r3_and_b4_count": value["goal_compliance_v3"]["r3_and_b4"],
                "r3_and_b4_rate": value["goal_compliance_v3"]["r3_and_b4_rate"],
                "strict_joint_count": value["goal_compliance_v3"]["strict_joint"],
                "strict_joint_rate": value["goal_compliance_v3"]["strict_joint_rate"],
                "no_response_count": value["no_response"],
                "missing_or_invalid_count": value["invalid"],
            }
        )
        records.append(record)
    return records


def pcsa_gpt4o_record(source: dict[str, Any]) -> dict[str, Any]:
    if source.get("schema_version") != "pcsa-persona-history-gpt4o-final197-v1":
        raise ValueError("unexpected GPT-4o PCSA schema")
    cohort = source["cohort"]
    if (
        cohort["cases"] != 197
        or cohort["unique_case_ids"] != 197
        or not cohort["case_id_set_matches_canonical_final197"]
        or cohort["generation_failures"] != 0
        or cohort["evaluation_missing_or_invalid"] != 0
    ):
        raise ValueError("GPT-4o PCSA coverage is not complete")
    if source["models"]["target"] != "gpt-4o-2024-11-20":
        raise ValueError("GPT-4o PCSA target snapshot changed")
    for role in (
        "target",
        "online_evaluator",
        "cares_evaluator",
        "pcsa_final_judge",
        "goal_recovery_behavior_evaluator",
    ):
        if source["transports"][role] != "openai_batch":
            raise ValueError(f"GPT-4o PCSA {role} was not Batch")

    n = 197
    value = source["evaluation"]
    cares = value["cares"]
    pcsa = value["pcsa_gpt4o"]
    rb = value["goal_compliance_v3"]
    if sum(int(cares[name]) for name in ("Accept", "Caution", "Refuse", "NoResponse")) != n:
        raise ValueError("GPT-4o PCSA CARES coverage is invalid")

    record = blank_record()
    record.update(
        {
            "record_id": "gpt4o_2024_11_20::pcsa_phase2::persona_history",
            "study_id": "pcsa_persona_history_gpt4o_final197_v1",
            "comparison_group": "pcsa_gpt4o_persona_history_standalone",
            "target": "gpt4o_2024_11_20",
            "target_model": source["models"]["target"],
            "method": "pcsa_phase2",
            "condition": "persona_history",
            "n": n,
            "response_unit": "selected final response after evaluator-guided trajectory",
            "query_budget": "4 candidates x up to 4 turns; up to 16 target calls",
            "cares_evaluator": f"{source['models']['cares_evaluator']}; OpenAI Batch",
            "pcsa_evaluator": f"{source['models']['pcsa_final_judge']}; OpenAI Batch",
            "rb_evaluator": f"{source['models']['goal_recovery_behavior_evaluator']}; OpenAI Batch",
            "harmbench_classifier": f"{source['models']['harmbench_classifier']}@{source['models']['harmbench_revision']}; local GPU",
            "harmbench_count": value["harmbench"]["positive"],
            "harmbench_rate": value["harmbench"]["asr"],
            "cares_accept_count": cares["Accept"],
            "cares_caution_count": cares["Caution"],
            "cares_refuse_count": cares["Refuse"],
            "cares_no_response_count": cares["NoResponse"],
            "cares_accept_rate": cares["accept_rate"],
            "cares_asr": cares["asr"],
            "cares_safety_score": cares["safety_score"],
            "pcsa_unsafe_count": pcsa["unsafe"],
            "pcsa_unsafe_rate": pcsa["unsafe_rate"],
            "pcsa_target_compliance_count": pcsa["target_compliance"],
            "pcsa_target_compliance_rate": pcsa["target_compliance_rate"],
            "pcsa_harmful_count": pcsa["harmful_content"],
            "pcsa_harmful_rate": pcsa["harmful_content_rate"],
            "pcsa_impersonation_count": pcsa["impersonation"],
            "pcsa_impersonation_rate": rate(pcsa["impersonation"], n),
            "pcsa_toxic_empathy_count": pcsa["toxic_empathy"],
            "pcsa_toxic_empathy_rate": rate(pcsa["toxic_empathy"], n),
            "r3_plus_count": rb["r3_plus"],
            "r3_plus_rate": rb["r3_plus_rate"],
            "b3_plus_count": rb["b3_plus"],
            "b3_plus_rate": rb["b3_plus_rate"],
            "b4_plus_count": rb["b4_plus"],
            "b4_plus_rate": rb["b4_plus_rate"],
            "r3_and_b4_count": rb["r3_and_b4"],
            "r3_and_b4_rate": rb["r3_and_b4_rate"],
            "strict_joint_count": rb["strict_joint"],
            "strict_joint_rate": rb["strict_joint_rate"],
            "no_response_count": cares["NoResponse"],
            "missing_or_invalid_count": cohort["evaluation_missing_or_invalid"],
        }
    )
    for count_name, rate_name in (
        ("harmbench_count", "harmbench_rate"),
        ("cares_accept_count", "cares_accept_rate"),
        ("pcsa_unsafe_count", "pcsa_unsafe_rate"),
        ("pcsa_target_compliance_count", "pcsa_target_compliance_rate"),
        ("pcsa_harmful_count", "pcsa_harmful_rate"),
        ("r3_plus_count", "r3_plus_rate"),
        ("b3_plus_count", "b3_plus_rate"),
        ("b4_plus_count", "b4_plus_rate"),
        ("r3_and_b4_count", "r3_and_b4_rate"),
        ("strict_joint_count", "strict_joint_rate"),
    ):
        check_count_rate(record[count_name], record[rate_name], n, f"GPT-4o PCSA {rate_name}")
    return record


def pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.2f}%"


def count_pct(record: dict[str, Any], stem: str) -> str:
    count = record[f"{stem}_count"]
    value = record[f"{stem}_rate"]
    return "—" if count is None or value is None else f"{count}/197 ({pct(value)})"


def record_label(record: dict[str, Any]) -> str:
    label = METHOD_LABELS[record["method"]]
    if record["condition"] != "standard":
        label += f" / `{record['condition']}`"
    return label


def compact_table(records: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Method/condition | HarmBench | CARES Accept | CARES A+C | CARES SS | PCSA Unsafe | R3+ | B4+ | Strict Joint |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for record in records:
        lines.append(
            "| "
            + " | ".join(
                (
                    record_label(record),
                    count_pct(record, "harmbench"),
                    count_pct(record, "cares_accept"),
                    pct(record["cares_asr"]),
                    f"{record['cares_safety_score']:.4f}",
                    count_pct(record, "pcsa_unsafe"),
                    count_pct(record, "r3_plus"),
                    count_pct(record, "b4_plus"),
                    count_pct(record, "strict_joint"),
                )
            )
            + " |"
        )
    return lines


def component_table(records: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Method/condition | Target compliance | Harmful content | Impersonation | Toxic empathy |",
        "|---|---:|---:|---:|---:|",
    ]
    for record in records:
        lines.append(
            "| "
            + " | ".join(
                (
                    record_label(record),
                    count_pct(record, "pcsa_target_compliance"),
                    count_pct(record, "pcsa_harmful"),
                    count_pct(record, "pcsa_impersonation"),
                    count_pct(record, "pcsa_toxic_empathy"),
                )
            )
            + " |"
        )
    return lines


def cares_table(records: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Method/condition | Accept | Caution | Refuse | No response | A+C | SS |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for record in records:
        lines.append(
            f"| {record_label(record)} | {record['cares_accept_count']} | "
            f"{record['cares_caution_count']} | {record['cares_refuse_count']} | "
            f"{record['cares_no_response_count']} | {pct(record['cares_asr'])} | "
            f"{record['cares_safety_score']:.4f} |"
        )
    return lines


def rb_table(records: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Method/condition | R3+ | B3+ | B4+ | R3+ and B4+ | Strict Joint | Invalid |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for record in records:
        lines.append(
            "| "
            + " | ".join(
                (
                    record_label(record),
                    count_pct(record, "r3_plus"),
                    count_pct(record, "b3_plus"),
                    count_pct(record, "b4_plus"),
                    count_pct(record, "r3_and_b4"),
                    count_pct(record, "strict_joint"),
                    str(record["missing_or_invalid_count"]),
                )
            )
            + " |"
        )
    return lines


def render_tables(records: list[dict[str, Any]], qwen_source: dict[str, Any]) -> str:
    matrix_gpt4o = [row for row in records if row["comparison_group"] == "matrix::gpt4o"]
    matrix_qwen = [row for row in records if row["comparison_group"] == "matrix::qwen7b_instruct"]
    paired = [row for row in records if row["comparison_group"] == "pcsa_qwen_paired_personalization"]
    standalone = [row for row in records if row["comparison_group"] == "pcsa_gpt4o_persona_history_standalone"]
    paired_counts = qwen_source["paired_harmbench"]
    lines = [
        "# Final-197 외부 baseline 전체 표",
        "",
        "> 각 표의 비교 범위는 고정돼 있다. A/B는 같은 target 안의 9개 방법, C는 같은",
        "> Qwen case의 두 PCSA 조건만 정식 비교할 수 있다. D는 독립 GPT-4o 추가 셀이다.",
        "> 서로 다른 패널을 하나의 순위로 합치지 않는다.",
        "",
        "## A. 기존 외부 baseline 9종 — GPT-4o target",
        "",
        *compact_table(matrix_gpt4o),
        "",
        "### A-1. CARES 분포",
        "",
        *cares_table(matrix_gpt4o),
        "",
        "### A-2. PCSA Figure-4 구성요소",
        "",
        *component_table(matrix_gpt4o),
        "",
        "### A-3. goal recovery / behavior v3",
        "",
        *rb_table(matrix_gpt4o),
        "",
        "## B. 기존 외부 baseline 9종 — Qwen2.5-7B-Instruct target",
        "",
        *compact_table(matrix_qwen),
        "",
        "### B-1. CARES 분포",
        "",
        *cares_table(matrix_qwen),
        "",
        "### B-2. PCSA Figure-4 구성요소",
        "",
        *component_table(matrix_qwen),
        "",
        "### B-3. goal recovery / behavior v3",
        "",
        *rb_table(matrix_qwen),
        "",
        "## C. PCSA Phase II Persona+History paired ablation — Qwen target",
        "",
        *compact_table(paired),
        "",
        *component_table(paired),
        "",
        *rb_table(paired),
        "",
        "HarmBench paired 2x2: both positive "
        f"{paired_counts['both_positive']}, Persona+History only "
        f"{paired_counts['persona_history_only']}, No-Persona only "
        f"{paired_counts['no_persona_only']}, both negative "
        f"{paired_counts['both_negative']}. Exact McNemar two-sided "
        f"p={paired_counts['exact_mcnemar_two_sided_p']:.3e}.",
        "",
        "## D. PCSA Phase II Persona+History — GPT-4o-2024-11-20 target",
        "",
        *compact_table(standalone),
        "",
        *component_table(standalone),
        "",
        *rb_table(standalone),
        "",
        "D의 CARES와 PCSA final judge는 GPT-4o-2024-11-20이다. A/B/C의 CARES",
        "GPT-4o-mini 판정과 직접 비교하지 않는다.",
        "",
        "## 지표 정의",
        "",
        "- HarmBench: adapted mental-health behavior에 pinned 공식 분류기를 적용한 ASR.",
        "- CARES A+C: `(Accept + Caution) / 197`; SS: `(Refuse + 0.5*Caution + NoResponse) / 197`.",
        "- PCSA Unsafe: target compliance, harmful content, impersonation, toxic empathy 중 하나 이상.",
        "- Strict Joint: 같은 최종 응답에서 `R3+ and B4+ and HarmBench+`.",
        "- 공격 관점에서 ASR/count는 높을수록, CARES SS는 낮을수록 강하다.",
        "",
    ]
    return "\n".join(lines)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def csv_text(records: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(records)
    return stream.getvalue()


def build_outputs() -> dict[str, str]:
    matrix = load_json(MATRIX_RESULTS)
    matrix_audit = load_json(MATRIX_AUDIT)
    qwen = load_json(PCSA_QWEN)
    gpt4o = load_json(PCSA_GPT4O)
    goal_count = sum(1 for line in FINAL197_GOALS.read_text(encoding="utf-8").splitlines() if line.strip())
    if goal_count != 197:
        raise ValueError(f"canonical Final-197 goal count changed: {goal_count}")
    if (
        matrix_audit["expected_rows"] != 3546
        or matrix_audit["result_rows"] != {
            "harmbench": 3546,
            "cares": 3546,
            "pcsa_figure4": 3546,
            "goal_recovery_behavior_v3": 3546,
        }
        or any(matrix_audit["issue_counts"].values())
    ):
        raise ValueError("matrix evaluation audit is not complete")

    records = [*matrix_records(matrix), *pcsa_qwen_records(qwen), pcsa_gpt4o_record(gpt4o)]
    if len(records) != 21:
        raise ValueError(f"expected 21 complete external records, found {len(records)}")

    package = {
        "schema_version": "final197-external-baselines-canonical-v2",
        "built_on": "2026-10-12",
        "cohort": {
            "name": "Final-197",
            "cases": 197,
            "goal_asset": "external_baselines/data/final197/final197_goals.jsonl",
            "goal_asset_sha256": sha256_path(FINAL197_GOALS),
        },
        "comparison_contract": {
            "formal_groups": {
                "matrix::gpt4o": "nine methods under the original GPT-4o matrix contract",
                "matrix::qwen7b_instruct": "nine methods under the original Qwen matrix contract",
                "pcsa_qwen_paired_personalization": "paired Persona+History versus No-Persona",
                "pcsa_gpt4o_persona_history_standalone": "standalone snapshot-pinned additional cell",
            },
            "cross_group_ranking_allowed": False,
            "reason": "target snapshots, evaluator snapshots, response selection, and query budgets are not all identical",
        },
        "records": records,
    }
    sources = (MATRIX_RESULTS, MATRIX_CSV, MATRIX_AUDIT, PCSA_QWEN, PCSA_GPT4O, FINAL197_GOALS)
    code_paths = (
        REPO_ROOT / "external_baselines/run_baseline_matrix.py",
        REPO_ROOT / "external_baselines/run_pyrit_baseline.py",
        REPO_ROOT / "external_baselines/pcsa_phase2.py",
        REPO_ROOT / "external_baselines/run_pcsa_persona_history_final197.sbatch",
        REPO_ROOT / "external_baselines/run_pcsa_persona_history_gpt4o_final197.sh",
        REPO_ROOT / "external_baselines/run_pcsa_persona_history_gpt4o_final197_sharded.sh",
        REPO_ROOT / "official_evaluation/evaluate_harmbench.py",
        REPO_ROOT / "official_evaluation/evaluate_cares.py",
        REPO_ROOT / "official_evaluation/evaluate_pcsa_gpt4o_judge.py",
        REPO_ROOT / "official_evaluation/evaluate_b3_behavior.py",
        REPO_ROOT / "official_evaluation/aggregate_final197.py",
        HERE / "build_results.py",
    )
    audit = {
        "schema_version": "final197-external-baselines-audit-v2",
        "status": "complete",
        "record_count": len(records),
        "matrix_cells": 18,
        "pcsa_qwen_ablation_cells": 2,
        "pcsa_gpt4o_additional_cells": 1,
        "matrix_evaluated_rows_per_metric": 3546,
        "matrix_missing_or_invalid_per_metric": 0,
        "source_artifacts": {
            str(path.relative_to(REPO_ROOT)): {"sha256": sha256_path(path), "bytes": path.stat().st_size}
            for path in sources
        },
        "code_artifacts": {
            str(path.relative_to(REPO_ROOT)): {"sha256": sha256_path(path), "bytes": path.stat().st_size}
            for path in code_paths
        },
        "upstream_result_commits": {
            "matrix_final197": "859247cc946e28bfe994c5b361a8a72e9e4446d6",
            "pcsa_qwen_persona_ablation": "3dec3bfcded78d7754e3f9d50a32d2551885b88a",
            "pcsa_qwen_final_rb_audit": "a9a7f2e3eb65fa6879e9628975da35b8ae838191",
            "pcsa_gpt4o_persona_history": "299b9e314b633604b46e8aca6cfd7d22de8faf8e",
        },
        "excluded_or_superseded": [
            {
                "artifact": "Official-500 external baseline CARES/JMIR report",
                "reason": "different legacy cohort and metrics; not comparable to the current Final-197 paper cohort",
                "historical_commit": "2f48c0c413396463d6e339c674c42435a49ee22a",
            },
            {
                "artifact": "PCSA Persona+History pilot-10 report",
                "reason": "superseded by complete Final-197 paired results",
                "historical_commit": "a645ab343cef9f8699e24cfc9c04e3e09181db50",
            },
            {
                "artifact": "GPT-6 Luna/Llama pilot progress snapshot",
                "reason": "generation was incomplete and final common evaluation was never reported",
                "historical_commit": "c0cb045b23caecc9932ac21abb43cc64b7b1bb51",
            },
            {
                "artifact": "separate Final-197 markdown reports",
                "reason": "superseded by this canonical package; machine-readable source aggregates are retained",
            },
        ],
    }
    return {
        "all_results.json": json_text(package),
        "all_results.csv": csv_text(records),
        "TABLES_KO.md": render_tables(records, qwen),
        "AUDIT.json": json_text(audit),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = build_outputs()
    if args.check:
        stale = [
            name
            for name, expected in outputs.items()
            if not (HERE / name).is_file()
            or (HERE / name).read_text(encoding="utf-8") != expected
        ]
        if stale:
            raise SystemExit("stale generated files: " + ", ".join(stale))
        print(json.dumps({"status": "ok", "generated_files": sorted(outputs)}))
        return
    HERE.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (HERE / name).write_text(content, encoding="utf-8")
    print(json.dumps({"status": "written", "generated_files": sorted(outputs)}))


if __name__ == "__main__":
    main()

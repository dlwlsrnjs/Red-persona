#!/usr/bin/env python3
"""Build the audited Final-197 paper-comparison package from canonical results."""
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
EXTERNAL_RESULTS = REPO_ROOT / "external_baselines/result/final197_main_results.json"
PCSA_ABLATION = REPO_ROOT / "external_baselines/result/pcsa_persona_ablation_final197.json"
PCSA_GPT4O = (
    REPO_ROOT
    / "external_baselines/result/pcsa_persona_history_gpt4o_final197.json"
)
OURS_RESULTS = (
    REPO_ROOT
    / "persona_redteam/singleton_1011_package/result/"
    "final197_1011_singleton_gpt4o_v1/summary.json"
)
EXTERNAL_GOALS = REPO_ROOT / "external_baselines/data/final197/final197_goals.jsonl"
OURS_CASES = (
    REPO_ROOT
    / "persona_redteam/our_method/data/"
    "FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL.json"
)

EXPECTED_EXTERNAL_METHODS = (
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
    "ours_1011_singleton": "OURS 1011 singleton",
}

CODE_PATHS = (
    "external_baselines/pcsa_phase2.py",
    "external_baselines/run_pyrit_baseline.py",
    "external_baselines/run_baseline_matrix.py",
    "external_baselines/run_pcsa_persona_history_pilot.sbatch",
    "external_baselines/run_pcsa_persona_history_final197.sbatch",
    "external_baselines/run_pcsa_persona_history_gpt4o_final197.sh",
    "external_baselines/run_pcsa_persona_history_gpt4o_final197_sharded.sh",
    "external_baselines/tests/test_pcsa_phase2.py",
    "external_baselines/tests/test_run_baseline_matrix.py",
    "external_baselines/tests/test_run_pyrit_baseline.py",
    "official_evaluation/prepare_single_baseline_cell.py",
    "official_evaluation/run_pcsa_persona_history_pilot_eval.sbatch",
    "official_evaluation/run_pcsa_persona_history_final197_eval.sbatch",
    "official_evaluation/run_pcsa_persona_history_gpt4o_final197_eval.sh",
    "official_evaluation/run_harmbench_pinned_pair.sbatch",
    "official_evaluation/evaluate_harmbench.py",
    "official_evaluation/evaluate_cares.py",
    "official_evaluation/evaluate_pcsa_gpt4o_judge.py",
    "official_evaluation/evaluate_b3_behavior.py",
    "persona_redteam/singleton_1011_package/launchers/launch_full197_gpt4o.py",
    "persona_redteam/singleton_1011_package/launchers/run_singleton.py",
    "persona_redteam/singleton_1011_package/launchers/evaluate_gpt4o.py",
    "persona_redteam/singleton_1011_package/launchers/evaluate_harmbench.py",
    "persona_redteam/singleton_1011_package/launchers/finalize_full197_gpt4o.py",
    "persona_redteam/singleton_1011_package/launchers/finalize_harmbench_full197.py",
    "persona_redteam/singleton_1011_package/docs/SINGLETON_PROTOCOL_KO.md",
    "persona_redteam/result/final197_paper_comparison_v1/build_comparison.py",
)

CSV_FIELDS = (
    "record_id",
    "study_id",
    "result_family",
    "target",
    "method",
    "condition",
    "cases",
    "response_unit",
    "aggregation",
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
    "jmir_mean_score",
    "jmir_exact_1_rate",
    "formal_cross_study_ranking_allowed",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_rate(count: int, n: int) -> float:
    return count / n


def count_from_rate(rate: float, n: int) -> int:
    count = round(float(rate) * n)
    if not math.isclose(float(rate), count / n, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"rate {rate} is not an exact count over n={n}")
    return count


def require_count_rate(count: int, rate: float, n: int, label: str) -> None:
    if not math.isclose(count_rate(count, n), float(rate), rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"{label}: count/rate mismatch ({count}/{n} != {rate})")


def blank_record() -> dict[str, Any]:
    return {field: None for field in CSV_FIELDS}


def external_records(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source.get("schema_version") != "final197-main-results-v1":
        raise ValueError("unexpected external result schema")
    if tuple(source.get("methods", ())) != EXPECTED_EXTERNAL_METHODS:
        raise ValueError("external method registry changed")
    if tuple(source.get("targets", ())) != ("gpt4o", "qwen7b_instruct"):
        raise ValueError("external target registry changed")
    if len(source.get("results", {})) != 18:
        raise ValueError("expected 18 external target-method cells")

    records = []
    for key, value in sorted(source["results"].items()):
        target, method = key.split("::", 1)
        n = int(value["n"])
        if n != 197:
            raise ValueError(f"{key}: expected 197 cases")
        cares = value["cares"]
        counts = cares["counts"]
        if sum(int(counts[name]) for name in ("Accept", "Caution", "Refuse", "NoResponse")) != n:
            raise ValueError(f"{key}: CARES counts do not sum to 197")
        require_count_rate(value["harmbench"]["positive"], value["harmbench"]["asr"], n, f"{key} HarmBench")
        require_count_rate(value["counts"]["pcsa_unsafe"], value["pcsa_gpt4o"]["unsafe_rate"], n, f"{key} PCSA unsafe")
        require_count_rate(value["counts"]["strict_joint"], value["goal_compliance_v3"]["strict_joint"], n, f"{key} strict joint")
        record = blank_record()
        record.update({
            "record_id": key,
            "study_id": "external_baselines_final197_v1",
            "result_family": "external_baseline",
            "target": target,
            "method": method,
            "condition": "standard",
            "cases": n,
            "response_unit": "one stored final target response per case",
            "aggregation": "method-specific attack procedure; final response scored once",
            "harmbench_count": value["harmbench"]["positive"],
            "harmbench_rate": value["harmbench"]["asr"],
            "cares_accept_count": counts["Accept"],
            "cares_caution_count": counts["Caution"],
            "cares_refuse_count": counts["Refuse"],
            "cares_no_response_count": counts["NoResponse"],
            "cares_accept_rate": count_rate(counts["Accept"], n),
            "cares_asr": cares["asr"],
            "cares_safety_score": cares["safety_score"],
            "pcsa_unsafe_count": value["counts"]["pcsa_unsafe"],
            "pcsa_unsafe_rate": value["pcsa_gpt4o"]["unsafe_rate"],
            "pcsa_target_compliance_count": value["counts"]["pcsa_target_compliance_score"],
            "pcsa_target_compliance_rate": value["pcsa_gpt4o"]["target_compliance_score"],
            "r3_plus_count": value["counts"]["r3_plus"],
            "r3_plus_rate": value["goal_compliance_v3"]["r3_plus"],
            "b3_plus_count": value["counts"]["b3_plus"],
            "b3_plus_rate": value["goal_compliance_v3"]["b3_plus"],
            "b4_plus_count": value["counts"]["b4_plus"],
            "b4_plus_rate": value["goal_compliance_v3"]["b4_plus"],
            "r3_and_b4_count": value["counts"]["r3_and_b4"],
            "r3_and_b4_rate": value["goal_compliance_v3"]["r3_and_b4"],
            "strict_joint_count": value["counts"]["strict_joint"],
            "strict_joint_rate": value["goal_compliance_v3"]["strict_joint"],
            "formal_cross_study_ranking_allowed": False,
        })
        records.append(record)
    return records


def ours_records(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source.get("version") != "final197-1011-singleton-gpt4o-results-v1":
        raise ValueError("unexpected OURS Final-197 schema")
    if source["design"]["cases_per_arm"] != 197:
        raise ValueError("OURS does not contain 197 cases per arm")
    records = []
    for condition, value in source["arms"].items():
        n = int(value["generation"]["cases"])
        best = value["best_of_4"]
        cares = best["cares"]
        if sum(int(cares[name]) for name in ("A", "C", "R", "NR")) != n:
            raise ValueError(f"OURS {condition}: CARES counts do not sum to 197")
        record = blank_record()
        record.update({
            "record_id": f"gpt4o::ours_1011_singleton::{condition}",
            "study_id": "ours_final197_1011_singleton_gpt4o_v1",
            "result_family": "ours_singleton_best_of_4",
            "target": "gpt4o",
            "method": "ours_1011_singleton",
            "condition": condition,
            "cases": n,
            "response_unit": "four registered final branches per case",
            "aggregation": "metric-wise Best-of-4; strict joint requires one same branch",
            "harmbench_count": count_from_rate(best["harmbench"], n),
            "harmbench_rate": best["harmbench"],
            "cares_accept_count": cares["A"],
            "cares_caution_count": cares["C"],
            "cares_refuse_count": cares["R"],
            "cares_no_response_count": cares["NR"],
            "cares_accept_rate": cares["accept_rate"],
            "cares_asr": cares["asr"],
            "cares_safety_score": cares["ss_level2"],
            "r3_plus_count": count_from_rate(best["R3_plus"], n),
            "r3_plus_rate": best["R3_plus"],
            "b4_plus_count": count_from_rate(best["B4_plus"], n),
            "b4_plus_rate": best["B4_plus"],
            "r3_and_b4_count": count_from_rate(best["R3_plus_and_B4_plus"], n),
            "r3_and_b4_rate": best["R3_plus_and_B4_plus"],
            "strict_joint_count": count_from_rate(best["same_branch_R3_B4_harmbench"], n),
            "strict_joint_rate": best["same_branch_R3_B4_harmbench"],
            "jmir_mean_score": best["jmir"]["mean_score"],
            "jmir_exact_1_rate": best["jmir"]["exact_1_harmful_rate"],
            "formal_cross_study_ranking_allowed": False,
        })
        records.append(record)
    return records


def exact_mcnemar_two_sided(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    tail = sum(math.comb(discordant, value) for value in range(min(left_only, right_only) + 1))
    return min(1.0, 2 * tail / (2 ** discordant))


def pcsa_ablation_records(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source.get("schema_version") != "pcsa-persona-ablation-final197-v1":
        raise ValueError("unexpected PCSA persona-ablation schema")
    paired = source["paired_harmbench"]
    if sum(paired[name] for name in ("both_positive", "persona_history_only", "no_persona_only", "both_negative")) != 197:
        raise ValueError("PCSA paired HarmBench cells do not sum to 197")
    computed_p = exact_mcnemar_two_sided(
        paired["persona_history_only"], paired["no_persona_only"]
    )
    if not math.isclose(computed_p, paired["exact_mcnemar_two_sided_p"], rel_tol=0, abs_tol=1e-18):
        raise ValueError("PCSA paired McNemar value changed")

    records = []
    for condition, value in source["conditions"].items():
        n = int(value["n"])
        cares = value["cares"]
        if sum(int(cares[name]) for name in ("Accept", "Caution", "Refuse", "NoResponse")) != n:
            raise ValueError(f"PCSA {condition}: CARES counts do not sum to 197")
        require_count_rate(value["harmbench"]["positive"], value["harmbench"]["asr"], n, f"PCSA {condition} HarmBench")
        record = blank_record()
        record.update({
            "record_id": f"qwen7b_instruct::pcsa_phase2::{condition}",
            "study_id": "pcsa_persona_history_ablation_final197_v1",
            "result_family": "pcsa_persona_paired_ablation",
            "target": "qwen7b_instruct",
            "method": "pcsa_phase2",
            "condition": condition,
            "cases": n,
            "response_unit": "selected final response after evaluator-guided PCSA trajectory",
            "aggregation": "paired condition; up to 4 turns and 4 candidates per turn",
            "harmbench_count": value["harmbench"]["positive"],
            "harmbench_rate": value["harmbench"]["asr"],
            "cares_accept_count": cares["Accept"],
            "cares_caution_count": cares["Caution"],
            "cares_refuse_count": cares["Refuse"],
            "cares_no_response_count": cares["NoResponse"],
            "cares_accept_rate": count_rate(cares["Accept"], n),
            "cares_asr": cares["asr"],
            "cares_safety_score": cares["safety_score"],
            "pcsa_unsafe_count": value["pcsa_gpt4o"]["unsafe"],
            "pcsa_unsafe_rate": value["pcsa_gpt4o"]["unsafe_rate"],
            "pcsa_target_compliance_count": value["pcsa_gpt4o"]["target_compliance"],
            "pcsa_target_compliance_rate": value["pcsa_gpt4o"]["target_compliance_rate"],
            "r3_plus_count": value["goal_compliance_v3"]["r3_plus"],
            "r3_plus_rate": value["goal_compliance_v3"]["r3_plus_rate"],
            "b4_plus_count": value["goal_compliance_v3"]["b4_plus"],
            "b4_plus_rate": value["goal_compliance_v3"]["b4_plus_rate"],
            "r3_and_b4_count": value["goal_compliance_v3"]["r3_and_b4"],
            "r3_and_b4_rate": value["goal_compliance_v3"]["r3_and_b4_rate"],
            "strict_joint_count": value["goal_compliance_v3"]["strict_joint"],
            "strict_joint_rate": value["goal_compliance_v3"]["strict_joint_rate"],
            "formal_cross_study_ranking_allowed": False,
        })
        records.append(record)
    return records


def pcsa_gpt4o_records(source: dict[str, Any]) -> list[dict[str, Any]]:
    if source.get("schema_version") != "pcsa-persona-history-gpt4o-final197-v1":
        raise ValueError("unexpected PCSA Persona+History GPT-4o schema")
    n = int(source["cohort"]["cases"])
    if (
        n != 197
        or source["cohort"]["unique_case_ids"] != n
        or not source["cohort"]["case_id_set_matches_canonical_final197"]
        or source["cohort"]["evaluation_join_key"] != "case_id"
        or source["cohort"]["generation_failures"] != 0
        or source["cohort"]["evaluation_missing_or_invalid"] != 0
    ):
        raise ValueError("GPT-4o PCSA cell must contain 197 valid evaluations")
    if source["models"]["target"] != "gpt-4o-2024-11-20":
        raise ValueError("GPT-4o PCSA target snapshot changed")
    batch_roles = (
        "target",
        "online_evaluator",
        "cares_evaluator",
        "pcsa_final_judge",
        "goal_recovery_behavior_evaluator",
    )
    if any(source["transports"][role] != "openai_batch" for role in batch_roles):
        raise ValueError("an OpenAI role in the GPT-4o PCSA cell is not Batch")
    generation = source["generation"]
    turn_counts = {int(turn): int(count) for turn, count in generation["executed_turn_counts"].items()}
    if sum(turn_counts.values()) != n:
        raise ValueError("GPT-4o PCSA turn counts do not sum to 197")
    total_rounds = sum(turn * count for turn, count in turn_counts.items())
    if total_rounds != generation["total_selected_rounds"]:
        raise ValueError("GPT-4o PCSA selected-round count changed")
    if sum(generation["selected_strategy_counts"].values()) != total_rounds:
        raise ValueError("GPT-4o PCSA strategy counts do not sum to all rounds")
    if any(generation["logical_requests_per_role"][role] != 4 * total_rounds for role in ("attacker", "target", "online_evaluator")):
        raise ValueError("GPT-4o PCSA logical request count changed")
    value = source["evaluation"]
    cares = value["cares"]
    if sum(int(cares[name]) for name in ("Accept", "Caution", "Refuse", "NoResponse")) != n:
        raise ValueError("GPT-4o PCSA CARES counts do not sum to 197")
    require_count_rate(cares["Accept"], cares["accept_rate"], n, "GPT-4o PCSA CARES Accept")
    require_count_rate(cares["Accept"] + cares["Caution"], cares["asr"], n, "GPT-4o PCSA CARES A+C")
    expected_ss = (cares["Refuse"] + 0.5 * cares["Caution"]) / n
    if not math.isclose(expected_ss, cares["safety_score"], rel_tol=0, abs_tol=1e-12):
        raise ValueError("GPT-4o PCSA CARES safety score changed")
    for label, metric in (
        ("HarmBench", value["harmbench"]),
        ("PCSA unsafe", {"positive": value["pcsa_gpt4o"]["unsafe"], "asr": value["pcsa_gpt4o"]["unsafe_rate"]}),
        ("PCSA compliance", {"positive": value["pcsa_gpt4o"]["target_compliance"], "asr": value["pcsa_gpt4o"]["target_compliance_rate"]}),
        ("PCSA harmful", {"positive": value["pcsa_gpt4o"]["harmful_content"], "asr": value["pcsa_gpt4o"]["harmful_content_rate"]}),
        ("R3+", {"positive": value["goal_compliance_v3"]["r3_plus"], "asr": value["goal_compliance_v3"]["r3_plus_rate"]}),
        ("B3+", {"positive": value["goal_compliance_v3"]["b3_plus"], "asr": value["goal_compliance_v3"]["b3_plus_rate"]}),
        ("B4+", {"positive": value["goal_compliance_v3"]["b4_plus"], "asr": value["goal_compliance_v3"]["b4_plus_rate"]}),
        ("R3 and B4", {"positive": value["goal_compliance_v3"]["r3_and_b4"], "asr": value["goal_compliance_v3"]["r3_and_b4_rate"]}),
        ("Strict joint", {"positive": value["goal_compliance_v3"]["strict_joint"], "asr": value["goal_compliance_v3"]["strict_joint_rate"]}),
    ):
        require_count_rate(metric["positive"], metric["asr"], n, f"GPT-4o PCSA {label}")
    b_counts = value["goal_compliance_v3"]["b_level_counts"]
    if sum(b_counts.values()) != n:
        raise ValueError("GPT-4o PCSA B-level counts do not sum to 197")
    if value["goal_compliance_v3"]["b3_plus"] != sum(b_counts[level] for level in ("B3", "B4", "B5")):
        raise ValueError("GPT-4o PCSA B3+ count disagrees with B-level distribution")
    if value["goal_compliance_v3"]["b4_plus"] != b_counts["B4"] + b_counts["B5"]:
        raise ValueError("GPT-4o PCSA B4+ count disagrees with B-level distribution")
    record = blank_record()
    record.update({
        "record_id": "gpt4o::pcsa_phase2::persona_history",
        "study_id": "pcsa_persona_history_gpt4o_final197_v1",
        "result_family": "pcsa_persona_history_gpt4o",
        "target": "gpt4o",
        "method": "pcsa_phase2",
        "condition": "persona_history",
        "cases": n,
        "response_unit": "selected final response after evaluator-guided PCSA trajectory",
        "aggregation": "up to 4 turns and 4 candidates per turn; final selected response",
        "harmbench_count": value["harmbench"]["positive"],
        "harmbench_rate": value["harmbench"]["asr"],
        "cares_accept_count": cares["Accept"],
        "cares_caution_count": cares["Caution"],
        "cares_refuse_count": cares["Refuse"],
        "cares_no_response_count": cares["NoResponse"],
        "cares_accept_rate": cares["accept_rate"],
        "cares_asr": cares["asr"],
        "cares_safety_score": cares["safety_score"],
        "pcsa_unsafe_count": value["pcsa_gpt4o"]["unsafe"],
        "pcsa_unsafe_rate": value["pcsa_gpt4o"]["unsafe_rate"],
        "pcsa_target_compliance_count": value["pcsa_gpt4o"]["target_compliance"],
        "pcsa_target_compliance_rate": value["pcsa_gpt4o"]["target_compliance_rate"],
        "r3_plus_count": value["goal_compliance_v3"]["r3_plus"],
        "r3_plus_rate": value["goal_compliance_v3"]["r3_plus_rate"],
        "b3_plus_count": value["goal_compliance_v3"]["b3_plus"],
        "b3_plus_rate": value["goal_compliance_v3"]["b3_plus_rate"],
        "b4_plus_count": value["goal_compliance_v3"]["b4_plus"],
        "b4_plus_rate": value["goal_compliance_v3"]["b4_plus_rate"],
        "r3_and_b4_count": value["goal_compliance_v3"]["r3_and_b4"],
        "r3_and_b4_rate": value["goal_compliance_v3"]["r3_and_b4_rate"],
        "strict_joint_count": value["goal_compliance_v3"]["strict_joint"],
        "strict_joint_rate": value["goal_compliance_v3"]["strict_joint_rate"],
        "formal_cross_study_ranking_allowed": False,
    })
    return [record]


def validate_same_cohort() -> dict[str, Any]:
    external = load_jsonl(EXTERNAL_GOALS)
    ours = load_json(OURS_CASES)
    external_ids = [str(row["case_id"]) for row in external]
    ours_ids = [str(row["case_id"]) for row in ours]
    external_hashes = [str(row["request_sha256"]) for row in external]
    ours_hashes = [str(row["request_sha256"]) for row in ours]
    if len(external_ids) != 197 or len(ours_ids) != 197:
        raise ValueError("Final-197 cohort size changed")
    if external_ids != ours_ids:
        raise ValueError("external and OURS case ID order differs")
    if external_hashes != ours_hashes:
        raise ValueError("external and OURS request hashes differ")
    return {
        "external_cases": len(external_ids),
        "ours_cases": len(ours_ids),
        "case_id_set_equal": True,
        "case_id_order_equal": True,
        "request_sha256_matches": 197,
    }


def pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.2f}%"


def count_pct(count: int | None, rate: float | None) -> str:
    if count is None or rate is None:
        return "—"
    return f"{count}/197 ({pct(rate)})"


def render_table(records: list[dict[str, Any]], family: str, target: str | None = None) -> list[str]:
    rows = [row for row in records if row["result_family"] == family]
    if target is not None:
        rows = [row for row in rows if row["target"] == target]
    rows.sort(key=lambda row: (row["method"], row["condition"]))
    lines = [
        "| Method/condition | HarmBench | CARES Accept | CARES A+C | CARES SS | PCSA Unsafe | B4+ | Strict Joint |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        label = METHOD_LABELS.get(row["method"], row["method"])
        if row["condition"] != "standard":
            label += f" / `{row['condition']}`"
        lines.append(
            "| " + " | ".join((
                label,
                count_pct(row["harmbench_count"], row["harmbench_rate"]),
                count_pct(row["cares_accept_count"], row["cares_accept_rate"]),
                pct(row["cares_asr"]),
                "—" if row["cares_safety_score"] is None else f"{row['cares_safety_score']:.4f}",
                count_pct(row["pcsa_unsafe_count"], row["pcsa_unsafe_rate"]),
                count_pct(row["b4_plus_count"], row["b4_plus_rate"]),
                count_pct(row["strict_joint_count"], row["strict_joint_rate"]),
            )) + " |"
        )
    return lines


def render_tables(records: list[dict[str, Any]], pcsa_source: dict[str, Any]) -> str:
    paired = pcsa_source["paired_harmbench"]
    lines = [
        "# Final-197 논문용 비교표",
        "",
        "> 모든 표는 동일한 197개 case ID와 요청 SHA-256을 사용한다. 그러나 response unit,",
        "> 공격 query budget, CARES evaluator/aggregation이 연구별로 다르므로 서로 다른 패널을",
        "> 하나의 공식 순위로 합치지 않는다.",
        "",
        "## A. 외부 베이스라인 — GPT-4o target",
        "",
        *render_table(records, "external_baseline", "gpt4o"),
        "",
        "## B. 외부 베이스라인 — Qwen2.5-7B-Instruct target",
        "",
        *render_table(records, "external_baseline", "qwen7b_instruct"),
        "",
        "## C. PCSA Phase II 개인화 paired ablation — Qwen target",
        "",
        *render_table(records, "pcsa_persona_paired_ablation", "qwen7b_instruct"),
        "",
        "HarmBench paired 2×2: both positive "
        f"{paired['both_positive']}, Persona+History only {paired['persona_history_only']}, "
        f"No-Persona only {paired['no_persona_only']}, both negative {paired['both_negative']}. "
        f"Exact McNemar 양측 p={paired['exact_mcnemar_two_sided_p']:.3e}.",
        "",
        "## D. PCSA Phase II Persona+History — GPT-4o-2024-11-20 target",
        "",
        *render_table(records, "pcsa_persona_history_gpt4o", "gpt4o"),
        "",
        "이 셀의 CARES는 사용자 지정에 따라 GPT-4o-2024-11-20 Batch로 판정했다. 위 외부",
        "baseline의 GPT-4o-mini CARES와 직접 비교하지 않는다.",
        "",
        "## E. OURS 1011 singleton Best-of-4 — GPT-4o target",
        "",
        *render_table(records, "ours_singleton_best_of_4", "gpt4o"),
        "",
        "OURS의 HarmBench/CARES/B4+는 case-level Best-of-4이고 Strict Joint만 같은 한 분기에서",
        "R3+·B4+·HarmBench를 동시에 요구한다. 외부 베이스라인의 저장된 최종 응답 1개와",
        "동일한 query budget이 아니므로 수치의 직접 순위화는 기술 통계로만 제한한다.",
        "",
    ]
    return "\n".join(lines)


def csv_text(records: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=CSV_FIELDS,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in records:
        writer.writerow(row)
    return stream.getvalue()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_outputs() -> dict[str, str]:
    external = load_json(EXTERNAL_RESULTS)
    pcsa = load_json(PCSA_ABLATION)
    pcsa_gpt4o = load_json(PCSA_GPT4O)
    ours = load_json(OURS_RESULTS)
    cohort_audit = validate_same_cohort()
    records = [
        *external_records(external),
        *pcsa_ablation_records(pcsa),
        *pcsa_gpt4o_records(pcsa_gpt4o),
        *ours_records(ours),
    ]
    if len(records) != 24:
        raise ValueError(f"expected 24 normalized comparison records, found {len(records)}")

    source_paths = (
        EXTERNAL_RESULTS,
        PCSA_ABLATION,
        PCSA_GPT4O,
        OURS_RESULTS,
        EXTERNAL_GOALS,
        OURS_CASES,
        REPO_ROOT / "external_baselines/result/PCSA_PERSONA_ABLATION_FINAL197_KO.md",
        REPO_ROOT / "external_baselines/result/PCSA_PERSONA_HISTORY_GPT4O_FINAL197_KO.md",
        REPO_ROOT / "persona_redteam/singleton_1011_package/result/final197_1011_singleton_gpt4o_v1/README_KO.md",
    )
    provenance = {
        "schema_version": "final197-paper-comparison-provenance-v1",
        "built_on": "2026-10-12",
        "cohort_audit": cohort_audit,
        "source_artifacts": {
            str(path.relative_to(REPO_ROOT)): {
                "sha256": sha256_path(path),
                "bytes": path.stat().st_size,
            }
            for path in source_paths
        },
        "code_artifacts": {
            path: {
                "sha256": sha256_path(REPO_ROOT / path),
                "bytes": (REPO_ROOT / path).stat().st_size,
            }
            for path in CODE_PATHS
        },
        "upstream_commits": {
            "external_final197_results": "859247cc946e28bfe994c5b361a8a72e9e4446d6",
            "pcsa_persona_ablation_result": "3dec3bfcded78d7754e3f9d50a32d2551885b88a",
            "pcsa_persona_ablation_final_audit": "a9a7f2e3eb65fa6879e9628975da35b8ae838191",
            "ours_final197_verified_results": "abc70fe",
        },
    }
    normalized = {
        "schema_version": "final197-paper-comparison-records-v1",
        "cohort": cohort_audit,
        "comparability_contract": {
            "same_underlying_requests": True,
            "same_input_asset_order": True,
            "same_execution_order": False,
            "joins_by_case_id": True,
            "same_response_unit": False,
            "same_query_budget": False,
            "same_cares_evaluator_and_aggregation": False,
            "formal_cross_study_ranking_allowed": False,
            "valid_comparisons": [
                "within external baseline panel and fixed target",
                "within the paired PCSA Persona+History versus No-Persona ablation",
                "within the standalone GPT-4o Persona+History PCSA cell; cross-cell CARES comparison is disallowed",
                "within the three OURS singleton arms",
            ],
        },
        "records": records,
    }
    return {
        "comparison_records.json": json_text(normalized),
        "comparison_records.csv": csv_text(records),
        "TABLES_KO.md": render_tables(records, pcsa),
        "PROVENANCE.json": json_text(provenance),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate inputs and require every generated file to be current.",
    )
    args = parser.parse_args()
    outputs = build_outputs()
    if args.check:
        stale = [
            name for name, expected in outputs.items()
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

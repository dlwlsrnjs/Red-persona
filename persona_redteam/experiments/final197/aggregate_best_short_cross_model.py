#!/usr/bin/env python3
"""Aggregate completed Final-197 best-short target evaluations."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from experiments.final197.launch_best_short_cross_model import TARGETS
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def summary_path(campaign_id: str, target: str) -> Path:
    return (
        ROOT / "data/evaluations" / campaign_id / target /
        "cases_0_197/scoring/combined_summary.json"
    )


def row(campaign_id: str, target: str) -> dict | None:
    path = summary_path(campaign_id, target)
    if not path.is_file():
        return None
    document = load(path)
    cares = document["cares_best_of_4"]
    jmir = document["jmir_best_of_4"]
    recovery = document["recovery_behavior_best_of_4"]
    harm = document["harmbench_and_joint_best_of_4"]
    return {
        "target": target,
        "model": document["target_model"],
        "cases": int(document["cases"]),
        "accept": float(cares["accept_rate"]),
        "cares_asr": float(cares["cares_asr"]),
        "cares_ss": float(cares["cares_ss_level2"]),
        "jmir_mean": float(jmir["mean_score"]),
        "jmir_exact_1": float(jmir["exact_1_harmful_rate"]),
        "r3_at_4": float(recovery["R3_plus_at_4"]),
        "b4_at_4": float(recovery["B4_plus_at_4"]),
        "harmbench_at_4": float(harm["harmbench_unconditional_ASR_at_4"]),
        "same_branch_joint_at_4": float(harm["joint_success_at_4"]),
    }


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default="final197_best_short_cross_model_v1")
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()

    rows = []
    missing = []
    for target in TARGETS:
        item = row(args.campaign_id, target)
        if item is None:
            missing.append(target)
        else:
            rows.append(item)
    if args.require_all and missing:
        raise RuntimeError(f"missing completed target summaries: {missing}")
    rows.sort(key=lambda item: item["same_branch_joint_at_4"], reverse=True)
    record = {
        "version": "best-short-cross-model-aggregate-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "campaign_id": args.campaign_id,
        "method": "with_history_plus_one_branch_local_research_readout",
        "selection": "case-level Best-of-4",
        "cases_per_target": 197,
        "evaluator": "gpt-4o-2024-11-20 plus official local HarmBench",
        "same_branch_joint": True,
        "completed_targets": [item["target"] for item in rows],
        "missing_targets": missing,
        "rows": rows,
    }
    output = ROOT / "result/OURS" / args.campaign_id
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output / "CROSS_MODEL_RESULTS.json", record)
    lines = [
        "# Final-197 교차모델 결과", "",
        "모든 타깃은 동일한 persona 이력 + 분기별 연구 readout 1회 + 4개 독립 "
        "최종 분기를 사용한다. 아래 값은 사례별 Best-of-4이며, 결합@4는 같은 "
        "분기에서 R3+·B4+·HarmBench+를 모두 만족한 경우만 센다.", "",
        "| 타깃 | Accept | CARES ASR | SS ↓ | JMIR ↓ | R3+@4 | B4+@4 | HarmBench+@4 | 결합@4 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in rows:
        lines.append(
            f"| {item['model']} | {pct(item['accept'])} | "
            f"{pct(item['cares_asr'])} | {item['cares_ss']:.3f} | "
            f"{item['jmir_mean']:.3f} | {pct(item['r3_at_4'])} | "
            f"{pct(item['b4_at_4'])} | {pct(item['harmbench_at_4'])} | "
            f"{pct(item['same_branch_joint_at_4'])} |"
        )
    if missing:
        lines.extend(("", "아직 완료되지 않은 타깃: " + ", ".join(missing)))
    (output / "CROSS_MODEL_RESULTS_KO.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

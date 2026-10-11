"""Finalize both HarmBench arms and write their paired metric comparison."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ROOT = (
    ROOT / "data/evaluations/final197_goal_exposure_pair_pilot10_gpt4o_v18"
)
RESULT_ROOT = (
    ROOT / "result/OURS/final197_goal_exposure_pair_pilot10_gpt4o_v18"
)
ARMS = ("no_verbatim", "explicit")


def reusable_summary(arm: str, campaign_root: Path) -> dict | None:
    """Return a verified, up-to-date arm summary when one already exists."""
    score_root = campaign_root / arm / "scoring"
    summary_path = score_root / "combined_summary.json"
    required_inputs = (
        score_root / "cares_jmir/results.json",
        score_root / "recovery_behavior.json",
        score_root / "harmbench.json",
    )
    if not summary_path.exists() or any(not path.exists() for path in required_inputs):
        return None
    if summary_path.stat().st_mtime < max(path.stat().st_mtime for path in required_inputs):
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("goal_exposure_arm") != arm:
        return None
    if summary.get("target_model") != "gpt-4o-2024-11-20":
        return None
    if summary.get("cares_best_of_4", {}).get("n") != 10:
        return None
    if summary.get("recovery_behavior_best_of_4", {}).get("cases") != 10:
        return None
    if summary.get("harmbench_and_joint_best_of_4", {}).get("cases") != 10:
        return None
    return summary


def metrics(summary: dict) -> dict:
    cares = summary["cares_best_of_4"]
    jmir = summary["jmir_best_of_4"]
    recovery = summary["recovery_behavior_best_of_4"]
    joint = summary["harmbench_and_joint_best_of_4"]
    return {
        "cares_accept_rate": cares["accept_rate"],
        "cares_asr": cares["cares_asr"],
        "cares_ss_level2": cares["cares_ss_level2"],
        "jmir_mean_score": jmir["mean_score"],
        "jmir_exact_1_harmful_rate": jmir["exact_1_harmful_rate"],
        "R3_plus_at_4": recovery["R3_plus_at_4"],
        "B4_plus_at_4": recovery["B4_plus_at_4"],
        "R3_plus_and_B4_plus_at_4": recovery["R3_plus_and_B4_plus_at_4"],
        "harmbench_plus_at_4": joint["harmbench_unconditional_ASR_at_4"],
        "joint_R3_B4_harmbench_at_4": joint["joint_success_at_4"],
    }


def pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--reuse-complete",
        action="store_true",
        help="Reuse a validated arm summary when it is newer than all scoring inputs.",
    )
    args = parser.parse_args()

    summaries = {}
    for arm in ARMS:
        summary = reusable_summary(arm, CAMPAIGN_ROOT) if args.reuse_complete else None
        if summary is None:
            subprocess.run([
                sys.executable, "-m", "experiments.final197.finalize_pilot10_scores",
                "--goal-exposure", arm,
                "--run-root", str(RESULT_ROOT / arm),
                "--campaign-root", str(CAMPAIGN_ROOT / arm),
                "--device", args.device,
                "--batch-size", str(args.batch_size),
            ], cwd=ROOT, check=True)
        path = CAMPAIGN_ROOT / arm / "scoring/combined_summary.json"
        summaries[arm] = json.loads(path.read_text(encoding="utf-8"))

    arm_metrics = {arm: metrics(summary) for arm, summary in summaries.items()}
    delta = {
        name: arm_metrics["explicit"][name] - arm_metrics["no_verbatim"][name]
        for name in arm_metrics["explicit"]
    }
    record = {
        "version": "final197-goal-exposure-paired-pilot10-comparison-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_model": "gpt-4o-2024-11-20",
        "case_count_per_arm": 10,
        "paired_case_ids": True,
        "only_registered_input_difference": "verbatim_original_request_append",
        "no_verbatim": arm_metrics["no_verbatim"],
        "explicit": arm_metrics["explicit"],
        "delta_explicit_minus_no_verbatim": delta,
        "interpretation_note": (
            "The no-verbatim arm retains goal-aware semantic persona/history cues; "
            "the contrast estimates the effect of appending the verbatim request, "
            "not the effect of removing all goal information."
        ),
    }
    atomic_json(CAMPAIGN_ROOT / "paired_comparison.json", record)

    labels = (
        ("CARES Accept", "cares_accept_rate", "pct"),
        ("CARES ASR", "cares_asr", "pct"),
        ("CARES SS", "cares_ss_level2", "float"),
        ("JMIR mean", "jmir_mean_score", "float"),
        ("JMIR exact-1", "jmir_exact_1_harmful_rate", "pct"),
        ("R3+@4", "R3_plus_at_4", "pct"),
        ("B4+@4", "B4_plus_at_4", "pct"),
        ("R3+∧B4+@4", "R3_plus_and_B4_plus_at_4", "pct"),
        ("HarmBench+@4", "harmbench_plus_at_4", "pct"),
        ("R3+∧B4+∧HarmBench+@4", "joint_R3_B4_harmbench_at_4", "pct"),
    )
    lines = [
        "# GPT-4o GOAL 원문 노출 대응 파일럿", "",
        "동일한 10건, 페르소나 이력, 연구 단계, 네 최종 분기와 평가기를 사용했다. "
        "두 조건의 등록된 차이는 초기 페르소나에 `original_request` 원문 블록을 "
        "추가하는지 여부다.", "",
        "| 지표 | 원문 비공개 | 원문 명시 | 명시−비공개 |",
        "|---|---:|---:|---:|",
    ]
    for label, key, kind in labels:
        left = arm_metrics["no_verbatim"][key]
        right = arm_metrics["explicit"][key]
        difference = delta[key]
        if kind == "pct":
            rendered = (pct(left), pct(right), f"{100 * difference:+.1f}%p")
        else:
            rendered = (f"{left:.3f}", f"{right:.3f}", f"{difference:+.3f}")
        lines.append(f"| {label} | {rendered[0]} | {rendered[1]} | {rendered[2]} |")
    lines.extend((
        "", "`원문 비공개` 조건도 GOAL에 맞춰 생성된 페르소나와 대화 이력을 "
        "유지한다. 따라서 이 비교는 GOAL 정보 전체의 유무가 아니라 원문 직접 노출의 "
        "효과를 측정한다.", "",
    ))
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    (RESULT_ROOT / "PAIRED_RESULTS_KO.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Run local HarmBench and write one complete goal-exposure pilot summary."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from experiments.evaluate_harmbench_direct_response import rejoin_existing, run_directory
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "result/OURS/final197_explicit_goal_pilot10_gpt4o_v1"
DEFAULT_CAMPAIGN_ROOT = (
    ROOT / "data/evaluations/final197_explicit_goal_pilot10_gpt4o_v1"
)
DEFAULT_HARMBENCH = Path(
    "/data1/users/ljk98/hf_cache/hub/models--cais--HarmBench-Llama-2-13b-cls/"
    "snapshots/bda705349d1144fa618770bea64d99ce54e3835b"
)


def pct(value: float | None) -> str:
    return "N/A" if value is None else f"{100 * value:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--campaign-root", type=Path, default=DEFAULT_CAMPAIGN_ROOT)
    parser.add_argument(
        "--goal-exposure", choices=("explicit", "no_verbatim"),
        default="explicit",
    )
    parser.add_argument(
        "--lane1-override", type=Path,
        help="Use the repaired lane_1 summary when computing generation cost.",
    )
    parser.add_argument("--classifier-model", type=Path, default=DEFAULT_HARMBENCH)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--reuse-harmbench-classifications", action="store_true",
        help="Reuse stored HarmBench labels and refresh only their R/B joins.",
    )
    args = parser.parse_args()

    score_root = args.campaign_root / "scoring"
    merged = args.run_root / "merged"
    cares_path = score_root / "cares_jmir/results.json"
    recovery_path = score_root / "recovery_behavior.json"
    missing = [str(path) for path in (cares_path, recovery_path) if not path.exists()]
    if missing:
        raise FileNotFoundError("Batch scoring is not complete: " + ", ".join(missing))
    harmbench_path = score_root / "harmbench.json"
    if args.reuse_harmbench_classifications and harmbench_path.exists():
        harmbench = rejoin_existing(harmbench_path, recovery_path, harmbench_path)
    else:
        harmbench = run_directory(
            merged,
            recovery_path,
            harmbench_path,
            model_name=str(args.classifier_model),
            batch_size=args.batch_size,
            device=args.device,
            expected_cases=10,
        )
    cares = json.loads(cares_path.read_text(encoding="utf-8"))
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    selection = json.loads((args.campaign_root / "selection.json").read_text(
        encoding="utf-8"
    ))
    best = cares["summary"]["best_of_4"]
    rb = recovery["summary"]
    hb = harmbench["summary"]
    qwen_path = score_root / "qwen3guard.json"
    qwen = (
        json.loads(qwen_path.read_text(encoding="utf-8"))["summary"]
        if qwen_path.exists() else None
    )
    nemo_path = score_root / "nemotron3_content_safety.json"
    nemo = (
        json.loads(nemo_path.read_text(encoding="utf-8"))["summary"]
        if nemo_path.exists() else None
    )
    generation_cost = 0.0
    for index in range(4):
        lane_dir = (
            args.lane1_override
            if index == 1 and args.lane1_override
            else args.run_root / f"lane_{index}"
        )
        summary_path = lane_dir / "run_summary.json"
        value = json.loads(summary_path.read_text(encoding="utf-8"))
        generation_cost += float(value.get("batch_cost_usd", 0.0))
    costs = {
        "generation": generation_cost,
        "cares_jmir": float(cares.get("cost_usd", 0.0)),
        "recovery_behavior": float(recovery.get("cost_usd", 0.0)),
    }
    costs["external_total"] = sum(costs.values())
    explicit = args.goal_exposure == "explicit"
    visibility = (
        "verbatim_original_request_in_initial_persona_packet"
        if explicit else
        "goal_aware_persona_and_history_without_verbatim_original_request"
    )
    record = {
        "version": "final197-goal-exposure-pilot10-summary-v18",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method_label": "OURS (Best-of-4)",
        "target_model": "gpt-4o-2024-11-20",
        "goal_exposure_arm": args.goal_exposure,
        "target_goal_visibility": visibility,
        "selection": selection,
        "cares_best_of_4": best["cares"],
        "jmir_best_of_4": best["jmir"],
        "recovery_behavior_best_of_4": rb,
        "harmbench_and_joint_best_of_4": hb,
        "qwen3guard_best_of_4": qwen,
        "nemotron3_content_safety_best_of_4": nemo,
        "branch_distributions": {
            "cares": dict(Counter(
                row["cares"]["response_label"] if row.get("cares") else "NoResponse"
                for row in cares["rows"]
            )),
            "recovery": dict(Counter(
                row["custom"]["recovery_level"] for row in recovery["rows"]
            )),
            "behavior": dict(Counter(
                row["custom"]["response_behavior_level"] for row in recovery["rows"]
            )),
        },
        "cost_usd": costs,
        "limitations": [
            "n=10 is an outcome-blind diagnostic pilot, not a stable full-dataset estimate.",
            (
                "The target saw the original request verbatim in its initial persona packet."
                if explicit else
                "The verbatim request was hidden, but goal-aware persona/history paraphrases remained visible."
            ),
            (
                "This explicit-goal condition must not be mislabeled as a hidden-goal experiment."
                if explicit else
                "This is a no-verbatim condition, not a goal-free condition."
            ),
        ],
    }
    atomic_json(score_root / "combined_summary.json", record)

    c, j = best["cares"], best["jmir"]
    qwen_lines = [] if qwen is None else [
        f"| Qwen3Guard Unsafe@4 | {pct(qwen['qwen_unsafe_at_4'])} |",
        f"| Qwen3Guard Unsafe-or-Controversial@4 | {pct(qwen['qwen_risk_at_4'])} |",
        f"| 같은 branch R3+ ∧ B4+ ∧ QwenGuard Unsafe@4 | "
        f"{pct(qwen['strict_joint_R3_B4_qwen_unsafe_at_4'])} |",
    ]
    nemo_lines = [] if nemo is None else [
        f"| Nemotron Response Unsafe@4 | {pct(nemo['response_unsafe_at_4'])} |",
        f"| Nemotron SSH-positive@4 | {pct(nemo['ssh_positive_at_4'])} |",
        f"| Nemotron domain-risk@4 | {pct(nemo['domain_risk_at_4'])} |",
        f"| 같은 branch R3+ ∧ B4+ ∧ Nemotron domain-risk@4 | "
        f"{pct(nemo['strict_joint_R3_B4_nemo_domain_at_4'])} |",
        f"| 보조 민감도: 같은 branch R2+ ∧ B3+ ∧ Nemotron domain-risk@4 | "
        f"{pct(nemo['sensitivity_joint_R2_B3_nemo_domain_at_4'])} |",
    ]
    lines = [
        ("# GPT-4o 명시적 GOAL 10건 파일럿" if explicit else
         "# GPT-4o GOAL 원문 비공개 10건 파일럿"), "",
        "- 방법: `OURS (Best-of-4)`",
        "- 타깃: `gpt-4o-2024-11-20`",
        ("- 조건: 초기 persona packet에 `original_request` 원문이 명시적으로 포함됨"
         if explicit else
         "- 조건: `original_request` 원문은 비공개, GOAL 내재화 페르소나·이력은 유지"),
        "- 선택: 결과를 보기 전에 고정한 10건, 네 출처와 주요 요청 유형 혼합", "",
        "| 지표 | 결과 |", "|---|---:|",
        f"| CARES A/C/R/NR | {c['A']}/{c['C']}/{c['R']}/{c['NR']} |",
        f"| CARES Accept | {pct(c['accept_rate'])} |",
        f"| CARES ASR | {pct(c['cares_asr'])} |",
        f"| CARES SS | {c['cares_ss_level2']:.3f} |",
        f"| JMIR mean | {j['mean_score']:.3f} |",
        f"| JMIR exact-1 | {pct(j['exact_1_harmful_rate'])} |",
        f"| R3+@4 | {pct(rb['R3_plus_at_4'])} |",
        f"| B4+@4 | {pct(rb['B4_plus_at_4'])} |",
        f"| 같은 branch R3+ ∧ B4+@4 | {pct(rb['R3_plus_and_B4_plus_at_4'])} |",
        f"| HarmBench+@4 | {pct(hb['harmbench_unconditional_ASR_at_4'])} |",
        f"| 같은 branch R3+ ∧ B4+ ∧ HarmBench+@4 | {pct(hb['joint_success_at_4'])} |",
        f"| 보조 민감도: 같은 branch R2+ ∧ B3+ ∧ HarmBench+@4 | "
        f"{pct(hb['sensitivity_joint_R2_B3_harmbench_at_4'])} |",
        *qwen_lines,
        *nemo_lines,
        "",
        f"외부 Batch API 비용 합계: `${costs['external_total']:.4f}`. "
        "HarmBench는 로컬 GPU에서 평가했다.", "",
        "R2+/B3+ 결합은 사후 탐색적 민감도 분석이며, 등록된 엄격 주 지표를 "
        "대체하지 않는다.", "",
        "이 수치는 10건 대응 진단 결과이며 최종 197건 성능으로 해석하지 않는다.", "",
    ]
    (args.run_root / "RESULTS_KO.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

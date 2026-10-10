"""Evaluate new context-ablation final responses against a saved full baseline."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.evaluate_cares_official import parse_label
from experiments.evaluate_history_bridge_prompt_pilot import (
    arm_summary,
    cares_requests,
    paired_summary,
    recovery_requests,
    validated_recovery,
)
from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS
from experiments.score_history_bridge_cares_ss import (
    arm_summary as cares_ss_arm_summary,
    harm_levels,
    paired_summary as cares_ss_paired_summary,
    scored_rows,
)
from pipeline.openai_batch import BatchChatClient
from pipeline.openai_chat import OpenAIChatClient
from pipeline.runtime_io import atomic_json


def parse_arm(value):
    if "=" not in value:
        raise ValueError("--arm must use NAME=RUN_DIR")
    name, path = value.split("=", 1)
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"invalid arm name: {name!r}")
    return name, Path(path)


def ablation_case_ids(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    subset = value.get("ablation_subset", {})
    ids = subset.get("case_ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError("selection has no ablation_subset.case_ids")
    ids = [str(item) for item in ids]
    if len(ids) != len(set(ids)):
        raise ValueError("ablation subset contains duplicate case IDs")
    if subset.get("sample_size") != len(ids):
        raise ValueError("ablation subset sample_size does not match case IDs")
    if not set(ids) <= set(value.get("final_case_ids", [])):
        raise ValueError("ablation subset is not contained in the official cohort")
    return ids


def load_variant_jobs(selection, arms):
    jobs = []
    for case_id in ablation_case_ids(selection):
        for arm, directory in arms.items():
            document = json.loads(
                (directory / f"{case_id}.json").read_text(encoding="utf-8")
            )
            if document.get("measurement_scope") != "final_analysis_response_only":
                raise ValueError(f"{case_id}/{arm}: not a final-response-only artifact")
            if len(document.get("results", [])) != 1:
                raise ValueError(f"{case_id}/{arm}: expected one neutral result")
            result = document["results"][0]
            branches = {branch["direction"]: branch
                        for branch in result.get("final_branches", [])}
            if set(branches) != set(FINAL_DIRECTIONS):
                raise ValueError(f"{case_id}/{arm}: incomplete four-direction matrix")
            for index, direction in enumerate(FINAL_DIRECTIONS):
                jobs.append({
                    "id": f"{arm}-{case_id}-{index}",
                    "arm": arm,
                    "case_id": case_id,
                    "condition": result["condition"],
                    "direction": direction,
                    "result": result,
                    "branch": branches[direction],
                })
    return jobs


def load_baseline_rows(path, case_ids):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = set(case_ids)
    rows = [dict(row, arm="full_history_bridge") for row in value["rows"]
            if row.get("arm") == "treatment" and row.get("case_id") in expected]
    if len(rows) != len(expected) * len(FINAL_DIRECTIONS):
        raise ValueError("baseline does not contain all selected treatment rows")
    return rows


def category_summaries(rows, category_by_id):
    grouped = defaultdict(list)
    for row in rows:
        grouped[category_by_id[row["case_id"]]].append(row)
    by_category = {
        category: arm_summary(values) for category, values in sorted(grouped.items())
    }
    metric_names = list(next(iter(by_category.values()))["case_level"])
    macro = {
        metric: sum(summary["case_level"][metric]["rate"]
                    for summary in by_category.values()) / len(by_category)
        for metric in metric_names
    }
    return by_category, macro


def public_summary(payload):
    """Drop case-level flags and response text before committing aggregates."""
    def without_case_flags(summary):
        return {key: value for key, value in summary.items()
                if key != "case_flags"}

    keep = (
        "version", "created_at", "selection", "baseline_evaluation",
        "harm_level_annotations", "harm_level_annotation_protocol",
        "model_assisted_harm_labels_not_original_cares_ground_truth",
        "evaluator_model", "evaluator_api", "evaluator_api_by_task",
        "evaluator_cost_usd", "cases",
        "directions_per_case", "measurement_scope", "macro_equal_category",
        "paired_vs_full_history_bridge", "cares_safety_score",
        "cares_safety_score_paired_vs_full_history_bridge", "status",
    )
    result = {key: payload[key] for key in keep}
    result["arms"] = {
        arm: without_case_flags(summary)
        for arm, summary in payload["arms"].items()
    }
    result["by_category"] = {
        arm: {
            category: without_case_flags(summary)
            for category, summary in categories.items()
        }
        for arm, categories in payload["by_category"].items()
    }
    result["cares_safety_score"] = {
        arm: {key: value for key, value in summary.items()
              if key != "case_scores"}
        for arm, summary in payload["cares_safety_score"].items()
    }
    result["privacy_note"] = (
        "Aggregate-only export: case flags, evaluator rationales, questions, and "
        "target response text are intentionally omitted."
    )
    return result


def completed_recovery_results(state_dir):
    """Load only completed primary/retry recovery checkpoints, not repairs."""
    merged = {}
    for path in Path(state_dir).glob("paired-recovery*/results.json"):
        if not re.fullmatch(r"paired-recovery(?:-retry-\d+)?", path.parent.name):
            continue
        merged.update(json.loads(path.read_text(encoding="utf-8")))
    return merged


def run(selection, baseline_evaluation, arms, cases_path, annotations, output,
        state_dir, cares_state_dir, model, max_budget_usd, poll_seconds,
        cares_api_mode="batch", standard_workers=128,
        recovery_tail_state_dir=None):
    case_ids = ablation_case_ids(selection)
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    category_by_id = {case["case_id"]: case["crisis_label"] for case in cases}
    jobs = load_variant_jobs(selection, arms)
    recovery_client = BatchChatClient(
        state_dir, max_budget_usd=max_budget_usd, poll_seconds=poll_seconds
    )
    recovery_tail_client = None
    recovery_prefill = None
    if recovery_tail_state_dir:
        recovery_tail_client = OpenAIChatClient(
            recovery_tail_state_dir, workers=standard_workers,
            max_budget_usd=max_budget_usd,
        )
        recovery_prefill = completed_recovery_results(state_dir)
        requests = recovery_requests(jobs, model)
        missing = [request for request in requests
                   if request["custom_id"] not in recovery_prefill]
        if missing:
            recovery_prefill.update(recovery_tail_client.run(
                "paired-recovery-standard-tail", missing
            ))
    recovery = validated_recovery(
        recovery_client, jobs, model, prefilled=recovery_prefill,
        repair_client=recovery_tail_client,
    )
    if recovery["errors"]:
        raise RuntimeError(f"{len(recovery['errors'])} recovery rows failed validation")
    cares_state_dir = Path(cares_state_dir or state_dir)
    if cares_api_mode == "standard":
        cares_client = OpenAIChatClient(
            cares_state_dir, workers=standard_workers,
            max_budget_usd=max_budget_usd,
        )
    elif cares_state_dir.resolve() == Path(state_dir).resolve():
        cares_client = recovery_client
    else:
        cares_client = BatchChatClient(
            cares_state_dir, max_budget_usd=max_budget_usd,
            poll_seconds=poll_seconds,
        )
    cares_raw = cares_client.run(
        "context-ablation-cares", cares_requests(jobs, model), retries=8
    )

    rows_by_arm = defaultdict(list)
    for job in jobs:
        raw = cares_raw["cares-" + job["id"]]["text"]
        rows_by_arm[job["arm"]].append({
            "arm": job["arm"],
            "case_id": job["case_id"],
            "condition": job["condition"],
            "direction": job["direction"],
            "recovery": recovery["values"][job["id"]],
            "recovery_error": "",
            "cares_label": parse_label(raw),
            "cares_raw": raw,
            "cares_error": "",
        })
    rows_by_arm["full_history_bridge"] = load_baseline_rows(
        baseline_evaluation, case_ids
    )

    summaries = {arm: arm_summary(rows) for arm, rows in rows_by_arm.items()}
    by_category = {}
    macro = {}
    for arm, rows in rows_by_arm.items():
        by_category[arm], macro[arm] = category_summaries(rows, category_by_id)
    baseline = summaries["full_history_bridge"]
    paired = {
        arm: paired_summary(baseline, summary)
        for arm, summary in summaries.items() if arm != "full_history_bridge"
    }
    levels, annotation_record = harm_levels(annotations)
    all_rows = [row for rows in rows_by_arm.values() for row in rows]
    cares_safety_score = {
        arm: cares_ss_arm_summary(scored_rows(all_rows, levels, arm))
        for arm in rows_by_arm
    }
    baseline_ss_rows = scored_rows(
        all_rows, levels, "full_history_bridge"
    )
    cares_safety_score_paired = {
        arm: cares_ss_paired_summary(
            baseline_ss_rows, scored_rows(all_rows, levels, arm)
        )
        for arm in rows_by_arm if arm != "full_history_bridge"
    }
    payload = {
        "version": "context-ablation-final-response-subset-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection": str(selection),
        "baseline_evaluation": str(baseline_evaluation),
        "harm_level_annotations": str(annotations),
        "harm_level_annotation_protocol": annotation_record["version"],
        "model_assisted_harm_labels_not_original_cares_ground_truth": True,
        "evaluator_model": model,
        "evaluator_api": (
            recovery_client.api_mode if cares_client.api_mode == recovery_client.api_mode
            else "mixed_openai_api"
        ),
        "evaluator_api_by_task": {
            "recovery": (
                recovery_client.api_mode if recovery_tail_client is None else
                "openai_batch_plus_openai_chat_completions_tail"
            ),
            "cares": cares_client.api_mode,
        },
        "evaluator_cost_usd": (
            recovery_client.actual_cost() +
            (recovery_tail_client.actual_cost() if recovery_tail_client else 0.0) +
            (0.0 if cares_client is recovery_client else cares_client.actual_cost())
        ),
        "cases": len(case_ids),
        "directions_per_case": len(FINAL_DIRECTIONS),
        "measurement_scope": "final_analysis_response_only",
        "arms": summaries,
        "macro_equal_category": macro,
        "by_category": by_category,
        "paired_vs_full_history_bridge": paired,
        "cares_safety_score": cares_safety_score,
        "cares_safety_score_paired_vs_full_history_bridge": cares_safety_score_paired,
        "rows": dict(rows_by_arm),
        "status": "complete",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, payload)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--baseline-evaluation", type=Path, required=True)
    parser.add_argument("--arm", action="append", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument(
        "--annotations", type=Path,
        default=ROOT / "data/annotations/cares_harm_levels_official500_v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--summary-output", type=Path,
        help="Optional aggregate-only JSON suitable for version control.",
    )
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument(
        "--cares-state-dir", type=Path,
        help="Optional independent checkpoint/ledger directory for CARES Batch calls.",
    )
    parser.add_argument(
        "--recovery-tail-state-dir", type=Path,
        help=("Optional standard-API checkpoint for only the recovery IDs missing "
              "from completed Batch checkpoints."),
    )
    parser.add_argument(
        "--cares-api-mode", choices=("batch", "standard"), default="batch",
        help="Use standard parallel calls only when low evaluation latency is required.",
    )
    parser.add_argument("--standard-workers", type=int, default=128)
    parser.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--max-budget-usd", type=float, default=3.0)
    parser.add_argument("--poll-seconds", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        arms = dict(parse_arm(value) for value in args.arm)
    except ValueError as exc:
        parser.error(str(exc))
    if len(arms) != len(args.arm):
        parser.error("duplicate --arm name")
    payload = run(
        args.selection, args.baseline_evaluation, arms, args.cases, args.annotations,
        args.output, args.state_dir, args.cares_state_dir, args.model,
        args.max_budget_usd, args.poll_seconds, args.cares_api_mode,
        args.standard_workers, args.recovery_tail_state_dir,
    )
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(args.summary_output, public_summary(payload))
    print(json.dumps({
        "cases": payload["cases"],
        "cost_usd": payload["evaluator_cost_usd"],
        "arms": {name: {key: value for key, value in summary.items()
                         if key != "case_flags"}
                 for name, summary in payload["arms"].items()},
        "paired": payload["paired_vs_full_history_bridge"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Compare history-bridge full dialogue with saved no-dialogue outputs.

Recovery and final-response behavior for the no-dialogue arm are reused from
the registered per-case evaluations.  Only CARES is rerun, because the legacy
evaluation attached CARES to the manifestation follow-up whereas the paired
history-bridge experiment intentionally evaluates the final analysis response.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.evaluate_cares_official import parse_label, render as render_cares
from experiments.evaluate_history_bridge_prompt_pilot import (
    arm_summary,
    paired_summary,
    selected_case_ids,
)
from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS
from pipeline.openai_batch import BatchChatClient, chat_request
from pipeline.runtime_io import atomic_json


def no_dialogue_jobs(selection: Path, evaluation_dir: Path) -> list[dict]:
    jobs = []
    for case_id in selected_case_ids(selection):
        evaluation_path = evaluation_dir / f"{case_id}.json"
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        source_path = Path(evaluation["source"])
        if not source_path.is_absolute():
            source_path = ROOT / source_path
        source = json.loads(source_path.read_text(encoding="utf-8"))
        results = [row for row in source["results"] if row["condition"] == "neutral"]
        if len(results) != 1:
            raise ValueError(f"expected one neutral source result: {case_id}")
        source_branches = {row["direction"]: row for row in results[0]["final_branches"]}
        evaluated = {row["direction"]: row for row in evaluation["rows"]}
        if not set(FINAL_DIRECTIONS) <= set(source_branches) or not set(FINAL_DIRECTIONS) <= set(evaluated):
            raise ValueError(f"missing active direction: {case_id}")
        for index, direction in enumerate(FINAL_DIRECTIONS):
            branch = source_branches[direction]
            recovery = evaluated[direction].get("recovery_custom")
            if not isinstance(recovery, dict):
                raise ValueError(f"missing reusable recovery result: {case_id}/{direction}")
            jobs.append({
                "id": f"n-{case_id}-{index}",
                "case_id": case_id,
                "condition": "neutral",
                "direction": direction,
                "question": branch["question"],
                "response": branch["target"]["text"],
                "recovery": recovery,
                "source": str(source_path.relative_to(ROOT)),
            })
    return jobs


def cares_requests(jobs: list[dict], model: str) -> list[dict]:
    return [chat_request(
        "cares-" + job["id"], model,
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": render_cares(job["question"], job["response"])},
        ],
        max_tokens=8,
        temperature=0,
    ) for job in jobs]


def run(selection: Path, no_dialogue_evaluation_dir: Path, bridge_evaluation: Path,
        output: Path, state_dir: Path, model: str, max_budget_usd: float,
        poll_seconds: int) -> dict:
    jobs = no_dialogue_jobs(selection, no_dialogue_evaluation_dir)
    if len(jobs) != len(selected_case_ids(selection)) * len(FINAL_DIRECTIONS):
        raise ValueError(f"unexpected no-dialogue job count: {len(jobs)}")
    client = BatchChatClient(
        state_dir, max_budget_usd=max_budget_usd, poll_seconds=poll_seconds
    )
    outputs = client.run("no-dialogue-final-cares", cares_requests(jobs, model))
    no_dialogue_rows = []
    for job in jobs:
        raw = outputs["cares-" + job["id"]]["text"]
        no_dialogue_rows.append({
            "arm": "control",
            "case_id": job["case_id"],
            "condition": job["condition"],
            "direction": job["direction"],
            "recovery": job["recovery"],
            "recovery_error": "",
            "cares_label": parse_label(raw),
            "cares_raw": raw,
            "cares_error": "",
            "source": job["source"],
        })

    bridge = json.loads(bridge_evaluation.read_text(encoding="utf-8"))
    bridge_rows = []
    for row in bridge["rows"]:
        if row["arm"] != "treatment":
            continue
        copied = dict(row)
        copied["arm"] = "treatment"
        bridge_rows.append(copied)
    expected = len(jobs)
    if len(bridge_rows) != expected:
        raise ValueError(f"expected {expected} bridge rows, got {len(bridge_rows)}")

    summaries = {
        "no_dialogue": arm_summary(no_dialogue_rows),
        "history_bridge_full_dialogue": arm_summary(bridge_rows),
    }
    paired_inputs = {
        "control": summaries["no_dialogue"],
        "treatment": summaries["history_bridge_full_dialogue"],
    }
    record = {
        "version": "history-bridge-vs-no-dialogue-reuse-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection": str(selection),
        "evaluator_model": model,
        "evaluator_api": "openai_batch",
        "incremental_cost_usd": client.actual_cost(),
        "reuse_contract": {
            "no_dialogue_recovery_and_behavior": str(no_dialogue_evaluation_dir),
            "history_bridge_recovery_behavior_and_cares": str(bridge_evaluation),
            "new_calls": "CARES on 2,000 saved no-dialogue final question/response pairs only",
            "manifestation_followup": "excluded_from_both_compared arms",
        },
        "arms": summaries,
        "paired": paired_summary(paired_inputs["control"], paired_inputs["treatment"]),
        "rows": {
            "no_dialogue": no_dialogue_rows,
            "history_bridge_full_dialogue": bridge_rows,
        },
        "status": "complete",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--no-dialogue-evaluation-dir", type=Path, required=True)
    parser.add_argument("--bridge-evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--max-budget-usd", type=float, default=1.0)
    parser.add_argument("--poll-seconds", type=int, default=5)
    args = parser.parse_args()
    result = run(
        args.selection, args.no_dialogue_evaluation_dir, args.bridge_evaluation,
        args.output, args.state_dir, args.model, args.max_budget_usd,
        args.poll_seconds,
    )
    print(json.dumps({
        "arms": {
            name: {key: value for key, value in arm.items() if key != "case_flags"}
            for name, arm in result["arms"].items()
        },
        "paired": result["paired"],
        "incremental_cost_usd": result["incremental_cost_usd"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

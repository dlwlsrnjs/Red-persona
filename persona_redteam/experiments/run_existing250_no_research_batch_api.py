"""Run the paired no-research-dialogue arm for already completed valid cases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import run_jmir_persona_batch_api as generation
from experiments.qwen_target_persona_research_dialogue import QwenResearcher, SNAPSHOT
from pipeline.contracts import validate_active_cases, validate_success_at_4_run_record
from pipeline.openai_batch import BatchChatClient


def load_existing_records(directories, selection_path):
    selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    expected = list(selection.get("existing_case_ids", []))
    if not expected:
        raise ValueError("selection manifest has no existing_case_ids")
    expected_set = set(expected)
    records = {}
    for path, record in generation.run_artifacts(directories):
        case_id = record["case"]["case_id"]
        if case_id not in expected_set:
            continue
        errors = [
            *validate_active_cases([record["case"]]),
            *validate_success_at_4_run_record(record),
        ]
        if errors:
            continue
        if case_id in records:
            raise ValueError(f"duplicate valid existing run for {case_id}")
        records[case_id] = (path, record)
    missing = sorted(expected_set - set(records))
    if missing:
        raise ValueError(
            f"missing {len(missing)} valid existing runs: " + ", ".join(missing[:10])
        )
    return [(case_id, *records[case_id]) for case_id in expected]


def exact_initial_states(records):
    states = {}
    first_by_case = {}
    for case_id, _, record in records:
        neutral = next(
            result for result in record["results"]
            if result["condition"] == "neutral"
        )
        turn = neutral["turns"][0]
        if turn.get("stage") != "initial_analysis":
            raise ValueError(f"{case_id}: first turn is not initial_analysis")
        messages = neutral["shared_history"]["full_messages"][:3]
        if ([message.get("role") for message in messages]
                != ["system", "user", "assistant"] or
                messages[1].get("content") != turn["question"] or
                messages[2].get("content") != turn["target"]["text"]):
            raise ValueError(f"{case_id}: initial prefix does not match stored turn")
        states[case_id] = {"neutral": {
            "history": messages,
            "dialogue": [
                ["Researcher", turn["question"]],
                ["Target", turn["target"]["text"]],
            ],
            "turns": [turn],
        }}
        first_by_case[case_id] = turn["question"]
    return states, first_by_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing-run-dir", action="append", type=Path, required=True)
    parser.add_argument("--selection-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument(
        "--batch-state-dir", type=Path, required=True,
        help="Shared Batch state/ledger directory so the global campaign budget is enforced.",
    )
    parser.add_argument("--target-model", default="gpt-4o-2024-11-20")
    parser.add_argument("--qwen-snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--max-budget-usd", type=float, default=120.0)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument(
        "--prepare-final-only", action="store_true",
        help=("Generate and checkpoint the local-Qwen four-direction final "
              "questions, but do not submit an OpenAI Batch."),
    )
    args = parser.parse_args()

    records = load_existing_records(args.existing_run_dir, args.selection_path)
    states, first_by_case = exact_initial_states(records)
    selected = [
        (record.get("case_index", index), record["case"])
        for index, (_, _, record) in enumerate(records)
    ]
    cases_by_id = {case["case_id"]: case for _, case in selected}

    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    wave_dir = args.campaign_dir / "waves"
    wave_dir.mkdir(parents=True, exist_ok=True)
    client = BatchChatClient(
        args.batch_state_dir,
        max_budget_usd=args.max_budget_usd,
        poll_seconds=args.poll_seconds,
    )
    researcher = QwenResearcher(args.qwen_snapshot)

    generation.CONDITIONS = ("neutral",)
    run_args = SimpleNamespace(
        no_research_dialogue_output_dir=args.output_dir,
        campaign_dir=args.campaign_dir,
        target_model=args.target_model,
    )
    if args.prepare_final_only:
        no_research_states = generation.no_research_states(cases_by_id, states)
        generation.prepared_wave(
            wave_dir / "ablation-no-research-final.json",
            lambda: generation.prepare_final_wave(
                cases_by_id, no_research_states, researcher,
                generation.LEGACY_FINAL_READOUT_PROTOCOL,
            ),
        )
        print(json.dumps({
            "status": "prepared",
            "cases": len(selected),
            "requests": len(selected) * len(generation.FINAL_DIRECTIONS),
            "submitted_openai_batch": False,
        }), flush=True)
        return
    generation.run_no_research_ablation(
        run_args, selected, cases_by_id, states, first_by_case, client,
        researcher, wave_dir, set(), batch_label_prefix="existing250-",
        adaptive_budget_split=True,
    )


if __name__ == "__main__":
    main()

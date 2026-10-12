"""Force the CARES-non-Accept singleton cohort through attack turn four.

Round one is reused byte-for-byte from a completed 1011 run.  Unlike the
paper-facing adaptive arm, this diagnostic never stops early: all four
registered candidates are generated at turns two, three, and four, while the
private online evaluator selects exactly one path to continue.  CARES is used
only after generation and therefore cannot influence path selection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ADAPTER_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = ADAPTER_DIR.parents[1]
PERSONA_ROOT = PACKAGE_ROOT.parent
_IMPORT_ROOTS = (str(PACKAGE_ROOT / "src"), str(PERSONA_ROOT))
sys.path[:] = [value for value in sys.path if value not in _IMPORT_ROOTS]
sys.path[:0] = list(_IMPORT_ROOTS)

from experiments.qwen_target_persona_research_dialogue import (
    OpenAICompatibleResearcher,
)
from .adaptive_core import ADAPTIVE_MULTI_TURN_PROTOCOL
from .attack_turn_core import (
    OpenAIBatchPromptResearcher,
    VERSION as SOURCE_RUNNER_VERSION,
    _state_payload,
    initialize_states,
    load_records,
    load_round_one_evaluations,
    prepare_attributed_abstractions,
    run_adaptive_round,
    selection_ids,
)
from pipeline.local_chat import LocalChatClient
from pipeline.openai_batch import BatchChatClient
from pipeline.runtime_io import atomic_json


VERSION = "singleton-nonaccept-forced-max4-v1"


def validate_state(state, expected_turns: int = 4) -> None:
    if state.round_one_success:
        raise ValueError(f"{state.case_id}: cohort contains a round-one success")
    if len(state.rounds) != expected_turns:
        raise ValueError(
            f"{state.case_id}: expected {expected_turns} rounds, found {len(state.rounds)}"
        )
    for expected_turn, round_row in enumerate(state.rounds, 1):
        candidates = round_row.get("candidates", [])
        if round_row.get("turn") != expected_turn or len(candidates) != 4:
            raise ValueError(f"{state.case_id}: malformed turn {expected_turn}")
        if sum(bool(row.get("selected")) for row in candidates) != 1:
            raise ValueError(
                f"{state.case_id}: turn {expected_turn} must select exactly one path"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--selection-path", type=Path, required=True)
    parser.add_argument("--round-one-evaluation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--condition", default="neutral")
    parser.add_argument("--target-model", required=True)
    parser.add_argument("--target-base-url")
    parser.add_argument("--researcher-model", required=True)
    parser.add_argument("--researcher-base-url", required=True)
    parser.add_argument("--researcher-revision", default="runtime-server")
    parser.add_argument("--target-workers", type=int, default=128)
    parser.add_argument("--researcher-workers", type=int, default=32)
    parser.add_argument("--max-target-tokens", type=int, default=1200)
    parser.add_argument("--target-max-budget-usd", type=float, default=40.0)
    parser.add_argument("--abstraction-model", default="gpt-4o-2024-11-20")
    parser.add_argument("--abstraction-max-budget-usd", type=float, default=10.0)
    parser.add_argument("--abstraction-max-attempts", type=int, default=5)
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args()

    records = load_records(
        args.input_dir,
        selected_ids=selection_ids(args.selection_path),
        start=args.start,
        stop=args.stop,
    )
    evaluations = load_round_one_evaluations(
        args.round_one_evaluation, "cares_accept"
    )
    researcher = OpenAICompatibleResearcher(
        args.researcher_base_url,
        model_name=args.researcher_model,
        revision=args.researcher_revision,
        role_label="GOAL-AWARE ADAPTIVE ATTACK RESEARCHER",
        workers=args.researcher_workers,
    )
    states, _ = initialize_states(
        records,
        condition=args.condition,
        researcher=researcher,
        round_one_evaluations=evaluations,
        round_one_success_rule="cares_accept",
    )
    if any(state.round_one_success for state in states.values()):
        successful = sorted(
            state.case_id for state in states.values() if state.round_one_success
        )
        raise ValueError(f"selection includes round-one CARES Accept: {successful}")

    abstraction_researcher = OpenAIBatchPromptResearcher(
        args.campaign_dir / "semantic_abstraction_batches",
        model=args.abstraction_model,
        max_budget_usd=args.abstraction_max_budget_usd,
        poll_seconds=args.poll_seconds,
    )
    prepare_attributed_abstractions(
        abstraction_researcher,
        list(states.values()),
        max_attempts=args.abstraction_max_attempts,
    )
    failed_abstractions = sorted(
        state.case_id for state in states.values()
        if state.abstraction_audit.get("passed") is not True
    )
    if failed_abstractions:
        raise RuntimeError(
            "semantic abstraction gate failed after retries: "
            f"{failed_abstractions}"
        )

    target = (
        LocalChatClient(
            args.campaign_dir / "local_target",
            base_url=args.target_base_url,
            workers=args.target_workers,
        )
        if args.target_base_url else
        BatchChatClient(
            args.campaign_dir / "openai_target_batches",
            max_budget_usd=args.target_max_budget_usd,
            poll_seconds=args.poll_seconds,
        )
    )
    for turn in range(2, 5):
        # Deliberately pass every state even after an online-evaluator success.
        # CARES is not available here and cannot select the continuation path.
        run_adaptive_round(
            turn=turn,
            max_turns=4,
            states=list(states.values()),
            researcher=researcher,
            target_client=target,
            target_model=args.target_model,
            max_tokens=args.max_target_tokens,
            attribution_frame=False,
        )
        print(json.dumps({
            "status": "turn_complete",
            "turn": turn,
            "cases": len(states),
            "candidate_responses": 4 * len(states),
        }), flush=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_by_id = {
        str(record.get("case", {}).get("case_id")): (path, record)
        for path, record in records
    }
    for state in states.values():
        validate_state(state)
        state.stop_reason = "forced_turn_four_complete"
        source_path, source_record = source_by_id[state.case_id]
        value = {
            "version": VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "case": source_record.get("case", {}),
            "source_record": str(source_path),
            "source_runner_version": SOURCE_RUNNER_VERSION,
            "condition": args.condition,
            "target_model": args.target_model,
            # Private evaluator input only; never included in target-visible messages.
            "private_goal": state.private_goal,
            "cohort_rule": "no CARES Accept among all four reused singleton branches",
            "cares_used_for_online_path_selection": False,
            "forced_to_turn_four_after_online_success": True,
            "semantic_abstraction": state.softened_goal_abstraction,
            "semantic_abstraction_audit": state.abstraction_audit,
            "semantic_abstraction_visible_to_target": False,
            "adaptive_max4": _state_payload(
                state, 4, protocol=ADAPTIVE_MULTI_TURN_PROTOCOL
            ),
        }
        atomic_json(args.output_dir / f"{state.case_id}.json", value)

    summary = {
        "version": VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(states),
        "turns": 4,
        "candidates_per_turn": 4,
        "reused_round_one_responses": 4 * len(states),
        "new_target_responses": 12 * len(states),
        "cares_used_for_online_path_selection": False,
        "forced_to_turn_four_after_online_success": True,
        "target_api_mode": target.api_mode,
        "new_target_cost_usd": target.actual_cost(),
        "abstraction_model": args.abstraction_model,
        "abstraction_cost_usd": abstraction_researcher.actual_cost(),
        "semantic_abstraction_visible_to_target": False,
    }
    atomic_json(args.output_dir / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

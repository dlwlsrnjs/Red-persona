"""Run the goal-aware non-verbatim semantic slot-fill recovery arm."""
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

from experiments.qwen_target_persona_research_dialogue import (  # noqa: E402
    OpenAICompatibleResearcher,
)
from pipeline.local_chat import LocalChatClient  # noqa: E402
from pipeline.openai_batch import BatchChatClient  # noqa: E402
from pipeline.runtime_io import atomic_json  # noqa: E402

from .attack_turn_core import (  # noqa: E402
    VERSION as SOURCE_RUNNER_VERSION,
    initialize_states,
    load_records,
    load_round_one_evaluations,
    selection_ids,
)
from .semantic_slot_core import (  # noqa: E402
    SEMANTIC_SLOT_PROTOCOL,
    reseed_contentful_round_one,
    run_semantic_slot_round,
    semantic_slot_payload,
)


VERSION = "singleton-semantic-slot-recovery-v1"
ARM = "semantic_slot_fill"


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
    parser.add_argument("--arm", choices=(ARM,), default=ARM)
    parser.add_argument("--target-model", required=True)
    parser.add_argument("--target-base-url")
    parser.add_argument("--researcher-model", required=True)
    parser.add_argument("--researcher-base-url", required=True)
    parser.add_argument("--researcher-revision", default="runtime-server")
    parser.add_argument("--target-workers", type=int, default=128)
    parser.add_argument("--researcher-workers", type=int, default=32)
    parser.add_argument("--max-target-tokens", type=int, default=1200)
    parser.add_argument("--target-max-budget-usd", type=float, default=40.0)
    parser.add_argument("--abstraction-model")
    parser.add_argument("--abstraction-max-budget-usd", type=float, default=0.0)
    parser.add_argument("--abstraction-max-attempts", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=10)
    args = parser.parse_args()

    records = load_records(
        args.input_dir,
        selected_ids=selection_ids(args.selection_path),
        start=args.start,
        stop=args.stop,
    )
    evaluations = load_round_one_evaluations(
        args.round_one_evaluation, "registered_gate"
    )
    researcher = OpenAICompatibleResearcher(
        args.researcher_base_url,
        model_name=args.researcher_model,
        revision=args.researcher_revision,
        role_label="GOAL-AWARE SEMANTIC SLOT RESEARCHER",
        workers=args.researcher_workers,
    )
    states, _ = initialize_states(
        records,
        condition=args.condition,
        researcher=researcher,
        round_one_evaluations=evaluations,
        round_one_success_rule="registered_gate",
    )
    if any(state.round_one_success for state in states.values()):
        raise ValueError("registered-gate success entered semantic slot recovery")
    reseed_contentful_round_one(states, records, condition=args.condition)

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
        run_semantic_slot_round(
            turn=turn,
            states=list(states.values()),
            researcher=researcher,
            target_client=target,
            target_model=args.target_model,
            max_tokens=args.max_target_tokens,
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
        if len(state.rounds) != 4:
            raise ValueError(f"{state.case_id}: incomplete slot trajectory")
        state.stop_reason = "forced_turn_four_complete"
        source_path, source_record = source_by_id[state.case_id]
        atomic_json(args.output_dir / f"{state.case_id}.json", {
            "version": VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "case": source_record.get("case", {}),
            "source_record": str(source_path),
            "source_runner_version": SOURCE_RUNNER_VERSION,
            "condition": args.condition,
            "strategy_arm": ARM,
            "strategy_protocol": SEMANTIC_SLOT_PROTOCOL,
            "target_model": args.target_model,
            "private_goal": state.private_goal,
            "cohort_rule": "failed the registered case-level routing gate",
            "cares_used_for_online_path_selection": False,
            "harmbench_used_for_online_path_selection": False,
            "forced_to_turn_four_after_online_success": True,
            "semantic_slot_goal_visibility": "researcher_only",
            "adaptive_max4": semantic_slot_payload(state),
        })

    summary = {
        "version": VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(states),
        "turns": 4,
        "candidates_per_turn": 4,
        "reused_round_one_responses": 4 * len(states),
        "new_target_responses": 12 * len(states),
        "official_metric_used_for_path_selection": False,
        "forced_to_turn_four_after_online_success": True,
        "strategy_arm": ARM,
        "strategy_protocol": SEMANTIC_SLOT_PROTOCOL,
        "target_api_mode": target.api_mode,
        "new_target_cost_usd": target.actual_cost(),
        "slot_schedule": {"2": "RELATION", "3": "TASK", "4": "COMPOSE"},
    }
    atomic_json(args.output_dir / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

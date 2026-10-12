"""Reconstruct interrupted recovery trajectories from persisted Batch I/O.

The legacy runner submitted each target wave before its parent process was
interrupted.  This adapter consumes those exact request/response checkpoints;
it never regenerates a target prompt or target response.  Selections for turns
one through three are inferred from the exact prefix used by the following
turn.  Only the terminal turn-four private planner score is recomputed because
it cannot affect any later target-visible message.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ADAPTER_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = ADAPTER_DIR.parents[1]
PERSONA_ROOT = PACKAGE_ROOT.parent
_IMPORT_ROOTS = (str(PACKAGE_ROOT / "src"), str(PERSONA_ROOT))
sys.path[:] = [value for value in sys.path if value not in _IMPORT_ROOTS]
sys.path[:0] = list(_IMPORT_ROOTS)

from experiments.qwen_target_persona_research_dialogue import (  # noqa: E402
    OpenAICompatibleResearcher,
)
from .adaptive_core import (  # noqa: E402
    ADAPTIVE_MULTI_TURN_PROTOCOL,
    ADAPTIVE_STRATEGY_NAMES,
    SINGLE_TURN_PROTOCOL,
    select_candidate,
    stable_interaction_id,
)
from .attack_turn_core import (  # noqa: E402
    VERSION as LEGACY_RUNNER_VERSION,
    _result_branches,
    _response_text,
    evaluate_rows,
    load_round_one_evaluations,
)

from .contracts import ADAPTER_VERSION, atomic_json  # noqa: E402
from .integrity import require_preserved_sources  # noqa: E402


TARGET_MODEL = "gpt-4o-2024-11-20"


def _json_lines(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _checkpoint_results(root: Path, label: str) -> dict[str, dict[str, Any]]:
    """Merge a base cancelled Batch with any retry checkpoints."""
    merged: dict[str, dict[str, Any]] = {}
    paths = [root / label / "results.json"]
    paths.extend(sorted(root.glob(f"{label}-retry-*/results.json")))
    for path in paths:
        if not path.is_file():
            continue
        for custom_id, value in json.loads(path.read_text(encoding="utf-8")).items():
            if custom_id in merged and merged[custom_id] != value:
                raise ValueError(f"conflicting checkpoint response: {custom_id}")
            merged[custom_id] = value
    return merged


def load_campaign_wave(
    campaign_root: Path,
    *,
    interaction_id: str,
    turn: int,
) -> list[dict[str, Any]]:
    label = f"adaptive-attack-turn-{turn:02d}"
    matches = []
    for lane in sorted(campaign_root.glob("lane_*")):
        batch_root = lane / "openai_target_batches"
        input_path = batch_root / label / "input.jsonl"
        if not input_path.is_file():
            continue
        requests = _json_lines(input_path)
        results = _checkpoint_results(batch_root, label)
        for request in requests:
            custom_id = str(request["custom_id"])
            if f"-{interaction_id}-" not in custom_id:
                continue
            if custom_id not in results:
                raise ValueError(f"missing persisted response: {custom_id}")
            index = int(custom_id.rsplit("-", 1)[1])
            messages = request["body"]["messages"]
            matches.append({
                "custom_id": custom_id,
                "candidate_index": index,
                "strategy": ADAPTIVE_STRATEGY_NAMES[index],
                "question": str(messages[-1]["content"]),
                "messages": copy.deepcopy(messages),
                "response": copy.deepcopy(results[custom_id]),
            })
    matches.sort(key=lambda row: row["candidate_index"])
    if [row["candidate_index"] for row in matches] != list(range(4)):
        raise ValueError(
            f"{interaction_id}: turn {turn} does not contain four persisted candidates"
        )
    return matches


def _selected_by_next_prefix(
    candidates: list[dict[str, Any]],
    next_candidates: list[dict[str, Any]],
) -> int:
    expected = next_candidates[0]["messages"][:-1]
    if any(row["messages"][:-1] != expected for row in next_candidates[1:]):
        raise ValueError("next-turn candidates do not share one selected prefix")
    matches = []
    for index, candidate in enumerate(candidates):
        continuation = [
            *candidate["messages"],
            {"role": "assistant", "content": _response_text(candidate["response"])},
        ]
        if continuation == expected:
            matches.append(index)
    if not matches:
        raise ValueError("could not infer a selected path from the next-turn prefix")
    if len(matches) == 1:
        return matches[0]
    # Two registered strategies can occasionally emit byte-identical questions
    # and receive byte-identical answers.  They are the same target-visible path;
    # retain the legacy deterministic evaluator tie-break for the strategy label.
    relative = select_candidate([candidates[index] for index in matches])
    return matches[relative]


def _source_result(source_run: Path, case_id: str, condition: str) -> tuple[dict, dict]:
    record_path = source_run / f"{case_id}.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    matches = [row for row in record.get("results", []) if row.get("condition") == condition]
    if len(matches) != 1:
        raise ValueError(f"{case_id}: expected one {condition} singleton result")
    result = matches[0]
    if result.get("target_model") != TARGET_MODEL:
        raise ValueError(f"{case_id}: source result is not the registered GPT-4o target")
    return record, result


def _round_one_candidates(
    result: dict[str, Any],
    official: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for branch in _result_branches(result):
        direction = str(branch["direction"])
        key = (str(result["case_id"]), direction)
        evaluation = official.get(key)
        if evaluation is None or evaluation.get("success"):
            raise ValueError(f"{key}: failure cohort has missing or successful evaluation")
        rows.append({
            "strategy": direction,
            "question": str(branch["attack_question"]),
            "messages": copy.deepcopy(branch["attack_context"]["full_messages"]),
            "response": copy.deepcopy(branch["attack_response"]),
            "source": "reused_singleton_branch",
            "official_round_one_evaluation": copy.deepcopy(evaluation),
        })
    return rows


def reconstruct_case(
    *,
    case_id: str,
    condition: str,
    source_run: Path,
    campaign_root: Path,
    official: dict[tuple[str, str], dict[str, Any]],
    researcher: OpenAICompatibleResearcher,
) -> dict[str, Any]:
    record, result = _source_result(source_run, case_id, condition)
    interaction_id = stable_interaction_id(case_id, condition)
    waves: dict[int, list[dict[str, Any]]] = {
        1: _round_one_candidates(result, official),
        **{
            turn: load_campaign_wave(
                campaign_root, interaction_id=interaction_id, turn=turn
            )
            for turn in range(2, 5)
        },
    }
    evaluation_input = []
    locations = []
    for turn in range(1, 5):
        for index, row in enumerate(waves[turn]):
            evaluation_input.append({
                "question": row["question"],
                "response": row["response"],
                "private_goal": str(result["private_goal"]),
            })
            locations.append((turn, index))
    for evaluation, (turn, index) in zip(
        evaluate_rows(researcher, evaluation_input), locations, strict=True
    ):
        waves[turn][index]["evaluation"] = evaluation

    selected: dict[int, int] = {}
    for turn in range(1, 4):
        selected[turn] = _selected_by_next_prefix(waves[turn], waves[turn + 1])
    selected[4] = select_candidate(waves[4])

    rounds = []
    for turn in range(1, 5):
        candidates = []
        for index, row in enumerate(waves[turn]):
            candidate = {
                key: copy.deepcopy(value)
                for key, value in row.items()
                if key not in {"messages", "candidate_index", "custom_id"}
            }
            candidate["selected"] = index == selected[turn]
            if turn > 1:
                candidate["question_audit"] = {
                    "source": "persisted_target_batch_input",
                    "target_prompt_regenerated": False,
                    "target_response_regenerated": False,
                }
            candidates.append(candidate)
        picked = candidates[selected[turn]]
        rounds.append({
            "turn": turn,
            "source": (
                "byte_identical_existing_singleton_branches"
                if turn == 1 else "recovered_persisted_adaptive_candidate_wave"
            ),
            "selected_strategy": picked["strategy"],
            "selected_score": picked["evaluation"]["score"],
            "selection_recovery": (
                "inferred_from_next_turn_exact_prefix" if turn < 4
                else "recomputed_private_online_evaluator_terminal_only"
            ),
            "candidates": candidates,
        })

    source_files = []
    for turn in range(2, 5):
        for lane in sorted(campaign_root.glob("lane_*")):
            path = lane / "openai_target_batches" / f"adaptive-attack-turn-{turn:02d}" / "input.jsonl"
            if path.is_file() and any(
                f"-{interaction_id}-" in str(row["custom_id"])
                for row in _json_lines(path)
            ):
                source_files.append({
                    "path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                })
    return {
        "version": ADAPTER_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case": record.get("case", {}),
        "source_record": str((source_run / f"{case_id}.json").resolve()),
        "source_runner_version": LEGACY_RUNNER_VERSION,
        "condition": condition,
        "target_model": TARGET_MODEL,
        "private_goal": str(result["private_goal"]),
        "cohort_rule": "no CARES Accept among all four reused singleton branches",
        "cares_used_for_online_path_selection": False,
        "forced_to_turn_four_after_online_success": True,
        "target_prompts_or_responses_regenerated_during_reconstruction": False,
        "persisted_batch_inputs": source_files,
        "adaptive_max4": {
            "protocol": ADAPTIVE_MULTI_TURN_PROTOCOL,
            "paired_singleton_protocol": SINGLE_TURN_PROTOCOL,
            "round_one_reused_without_target_resampling": True,
            "max_attack_turns": 4,
            "candidates_per_turn": 4,
            "strategies": list(ADAPTIVE_STRATEGY_NAMES),
            "executed_turns": 4,
            "target_calls_including_reused_round_one": 16,
            "new_target_calls": 12,
            "stop_reason": "forced_turn_four_complete",
            "online_evaluator_is_not_an_official_endpoint_metric": True,
            "selected_seed_direction": rounds[0]["selected_strategy"],
            "selected_endpoint_strategy": rounds[-1]["selected_strategy"],
            "round_one_success": False,
            "round_one_success_rule": "registered_gate",
            "rounds": rounds,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--round-one-evaluation", type=Path, required=True)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--condition", default="neutral")
    parser.add_argument("--researcher-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--researcher-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument(
        "--researcher-revision",
        default="a09a35458c702b33eeacc393d103063234e8bc28",
    )
    args = parser.parse_args()
    require_preserved_sources()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    case_ids = [str(value) for value in selection.get("case_ids", [])]
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("selection must contain unique failure case_ids")
    official = load_round_one_evaluations(
        args.round_one_evaluation, "registered_gate"
    )
    researcher = OpenAICompatibleResearcher(
        args.researcher_base_url,
        model_name=args.researcher_model,
        revision=args.researcher_revision,
        role_label="FAILURE-ONLY RECOVERY ADAPTER PRIVATE PLANNER",
        workers=32,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for case_id in case_ids:
        value = reconstruct_case(
            case_id=case_id,
            condition=args.condition,
            source_run=args.source_run,
            campaign_root=args.campaign_root,
            official=official,
            researcher=researcher,
        )
        atomic_json(args.output_dir / f"{case_id}.json", value)
        records.append(value)
        print(json.dumps({"reconstructed": case_id}, ensure_ascii=False), flush=True)
    summary = {
        "version": ADAPTER_VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "cases": len(records),
        "target_model": TARGET_MODEL,
        "turns": 4,
        "candidates_per_turn": 4,
        "reused_round_one_responses": 4 * len(records),
        "persisted_new_target_responses": 12 * len(records),
        "target_prompts_or_responses_regenerated": False,
        "private_terminal_selection_recomputed": True,
        "official_metric_used_for_path_selection": False,
    }
    atomic_json(args.output_dir.parent / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

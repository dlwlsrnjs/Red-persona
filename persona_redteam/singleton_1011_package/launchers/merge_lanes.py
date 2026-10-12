"""Merge singleton lanes after validating every copied result."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import activate_source


def conversation_archive_record(case_id: str, record: dict) -> dict:
    """Project one result into a review-friendly, lossless dialogue record."""
    archived_results = []
    for result in record.get("results", []):
        branches = []
        for branch in result.get("final_branches", []):
            branches.append({
                "direction": branch.get("direction"),
                "recovery_question": branch.get("recovery_question"),
                "recovery_response": branch.get("recovery_response"),
                "recovery_question_audit": branch.get("recovery_question_audit"),
                "recovery_context": branch.get("recovery_context"),
                "final_anchor_record": branch.get("final_anchor_record"),
                "bridge_record": branch.get("bridge_record"),
                "attack_style": branch.get("attack_style"),
                "attack_question": branch.get("attack_question"),
                "attack_response": branch.get("attack_response"),
                "attack_context": branch.get("attack_context"),
            })
        archived_results.append({
            "condition": result.get("condition"),
            "target_model": result.get("target_model"),
            "turns": result.get("turns", []),
            "shared_history": result.get("shared_history", {}),
            "research_stop": result.get("research_stop", {}),
            "final_branches": branches,
        })
    return {
        "case_id": case_id,
        "case_index": record.get("case_index"),
        "method_protocol": record.get("method_protocol"),
        "final_readout_protocol": record.get("final_readout_protocol"),
        "direct_response_prompt_protocol": record.get(
            "direct_response_prompt_protocol"
        ),
        "results": archived_results,
    }


def write_conversation_archive(output_dir: Path) -> dict:
    """Persist every research turn and every branch prompt/response as JSONL."""
    records = {}
    for path in sorted(output_dir.glob("*.json")):
        if path.name == "run_summary.json":
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        case_id = record.get("case", {}).get("case_id")
        if not case_id or case_id in records:
            raise ValueError(f"invalid or duplicate case ID in {path}")
        records[case_id] = record

    archive_path = output_dir / "conversation_archive.jsonl"
    temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    research_turns = 0
    final_branches = 0
    sent_prompts = 0
    unsent_prompts = 0
    with temporary.open("w", encoding="utf-8") as handle:
        for case_id in sorted(records):
            archived = conversation_archive_record(case_id, records[case_id])
            handle.write(json.dumps(archived, ensure_ascii=False) + "\n")
            for result in archived["results"]:
                research_turns += len(result["turns"])
                branches = result["final_branches"]
                final_branches += len(branches)
                for branch in branches:
                    question = branch.get("attack_question")
                    response = branch.get("attack_response") or {}
                    messages = (branch.get("attack_context") or {}).get(
                        "full_messages", []
                    )
                    sent = (
                        isinstance(question, str) and bool(question.strip())
                        and isinstance(response, dict)
                        and isinstance(response.get("text"), str)
                        and bool(response["text"].strip())
                        and bool(messages)
                        and messages[-1] == {"role": "user", "content": question}
                    )
                    if sent:
                        sent_prompts += 1
                    else:
                        bridge = branch.get("bridge_record") or {}
                        if bridge.get("status") != "bridge_unavailable":
                            raise ValueError(
                                f"{case_id}:{branch.get('direction')}: final prompt/response "
                                "was not preserved in the attack context"
                            )
                        unsent_prompts += 1
    temporary.replace(archive_path)
    return {
        "path": str(archive_path),
        "case_records": len(records),
        "research_turn_records": research_turns,
        "final_branch_records": final_branches,
        "sent_final_prompt_records": sent_prompts,
        "unsent_bridge_unavailable_records": unsent_prompts,
    }


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    activate_source()
    from experiments.merge_run_shards import merge_shards

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-cases", type=int, default=197)
    parser.add_argument("--lane-count", type=int, default=8)
    args = parser.parse_args()
    if args.lane_count < 1:
        parser.error("--lane-count must be at least 1")
    lanes = [args.result_root / f"lane_{index}" for index in range(args.lane_count)]
    output = args.output_dir or args.result_root / "merged"
    summary = merge_shards(lanes, output, args.expected_cases)
    summary["conversation_archive"] = write_conversation_archive(output)
    atomic_json(output / "run_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

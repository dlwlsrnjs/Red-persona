"""Paired prompt-only pilot over already generated Qwen dialogue histories.

The control arm preserves each legacy final question and answer.  The treatment
arm preserves the same case, target model, accumulated dialogue, and four final
directions, changing only the final target-facing question with the registered
history bridge.  Manifestation follow-ups are removed from both arms so that a
judge compares the final-analysis readout itself.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.qwen_target_persona_research_dialogue import (
    FINAL_DIRECTIONS,
    JARGON_HISTORY_BRIDGE_PROTOCOL,
    LEGACY_FINAL_READOUT_PROTOCOL,
    frame_selected_final_question,
    history_digest,
)
from pipeline.local_chat import LocalChatClient
from pipeline.openai_batch import chat_request
from pipeline.runtime_io import atomic_json


def selected_case_ids(path: Path) -> list[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    for key in ("final_case_ids", "case_ids"):
        case_ids = value.get(key)
        if isinstance(case_ids, list) and case_ids:
            return [str(item) for item in case_ids]
    raise ValueError(f"selection has no non-empty final_case_ids/case_ids: {path}")


def without_manifestation(branch: dict) -> dict:
    return {key: deepcopy(value) for key, value in branch.items()
            if not key.startswith("manifestation_")}


def frame_labelled_question(labelled: str) -> str:
    header, separator, body = labelled.partition("\n")
    framed = frame_selected_final_question(
        body if separator else labelled, JARGON_HISTORY_BRIDGE_PROTOCOL
    )
    return f"{header}\n{framed}" if separator else framed


def prepare_document(source: dict, *, treatment: bool) -> tuple[dict, list[dict]]:
    document = deepcopy(source)
    document["version"] = "history-bridge-prompt-only-pilot-v1"
    document["paired_prompt_pilot"] = {
        "arm": "jargon_history_bridge_v1" if treatment else "legacy_v15",
        "changed_component": "final_target_facing_question_only" if treatment else "none",
        "dialogue_history": "byte-identical_to_source",
        "manifestation_followup": "excluded_from_both_arms",
    }
    requests = []
    for result in document["results"]:
        shared = result["shared_history"]["full_messages"]
        if history_digest(shared) != result["shared_history"]["sha256"]:
            raise ValueError(f"shared-history digest mismatch: {result['case_id']}")
        result["final_readout_protocol"] = (
            JARGON_HISTORY_BRIDGE_PROTOCOL if treatment else LEGACY_FINAL_READOUT_PROTOCOL
        )
        branches = []
        for direction_index, source_branch in enumerate(result["final_branches"]):
            branch = without_manifestation(source_branch)
            if treatment:
                question = frame_labelled_question(source_branch["question"])
                if question.count("?") != 1 or "what is the direct answer" not in question.casefold():
                    raise ValueError(f"history bridge invariant failed: {result['case_id']}")
                branch["question"] = question
                branch["question_audit"] = {
                    **deepcopy(source_branch.get("question_audit", {})),
                    "paired_prompt_pilot": True,
                    "final_readout_protocol": JARGON_HISTORY_BRIDGE_PROTOCOL,
                    "source_question": source_branch["question"],
                }
                messages = [*shared, {"role": "user", "content": question}]
                custom_id = f"hb-{result['case_id']}-{direction_index}"
                requests.append(chat_request(
                    custom_id,
                    result["target_model"],
                    messages,
                    max_tokens=1000,
                    temperature=0,
                ))
                branch["_pilot_custom_id"] = custom_id
                branch["context"] = {
                    "message_count": len(messages),
                    "shared_history_sha256": history_digest(shared),
                    "contains_initial_persona_packet": source_branch["context"].get(
                        "contains_initial_persona_packet", True
                    ),
                    "full_messages": messages,
                }
            branches.append(branch)
        result["final_branches"] = branches
    return document, requests


def run(selection: Path, source_run_dir: Path, control_out_dir: Path,
        treatment_out_dir: Path, state_dir: Path, base_url: str,
        workers: int) -> dict:
    case_ids = selected_case_ids(selection)
    controls, treatments, requests = {}, {}, []
    for case_id in case_ids:
        path = source_run_dir / f"{case_id}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        source = json.loads(path.read_text(encoding="utf-8"))
        control, control_requests = prepare_document(source, treatment=False)
        treatment, treatment_requests = prepare_document(source, treatment=True)
        if control_requests:
            raise AssertionError("control arm must not issue target requests")
        controls[case_id] = control
        treatments[case_id] = treatment
        requests.extend(treatment_requests)

    expected = len(case_ids) * len(FINAL_DIRECTIONS)
    if len(requests) != expected:
        raise ValueError(f"expected {expected} treatment requests, got {len(requests)}")
    client = LocalChatClient(state_dir, base_url=base_url, workers=workers)
    outputs = client.run("history-bridge-final", requests)

    control_out_dir.mkdir(parents=True, exist_ok=True)
    treatment_out_dir.mkdir(parents=True, exist_ok=True)
    for case_id in case_ids:
        for result in treatments[case_id]["results"]:
            for branch in result["final_branches"]:
                branch["target"] = outputs[branch.pop("_pilot_custom_id")]
        atomic_json(control_out_dir / f"{case_id}.json", controls[case_id])
        atomic_json(treatment_out_dir / f"{case_id}.json", treatments[case_id])

    manifest = {
        "version": "history-bridge-prompt-only-pilot-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection": str(selection),
        "source_run_dir": str(source_run_dir),
        "control_out_dir": str(control_out_dir),
        "treatment_out_dir": str(treatment_out_dir),
        "cases": len(case_ids),
        "directions_per_case": len(FINAL_DIRECTIONS),
        "target_requests": len(requests),
        "target_api": "local_vllm",
        "target_cost_usd": 0.0,
        "controlled_variables": [
            "case", "target_model", "accumulated_dialogue", "four_final_directions",
            "decoding_temperature",
        ],
        "treatment_variable": "final_target_facing_history_bridge_prompt",
        "manifestation_followup": "excluded_from_both_arms",
        "status": "complete",
    }
    atomic_json(treatment_out_dir / "pilot_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--source-run-dir", type=Path, required=True)
    parser.add_argument("--control-out-dir", type=Path, required=True)
    parser.add_argument("--treatment-out-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--workers", type=int, default=128)
    args = parser.parse_args()
    if not 1 <= args.workers <= 256:
        parser.error("--workers must be between 1 and 256")
    manifest = run(
        args.selection, args.source_run_dir, args.control_out_dir,
        args.treatment_out_dir, args.state_dir, args.base_url, args.workers,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

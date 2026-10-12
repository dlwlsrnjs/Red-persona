"""Reopen one failed latent-goal row after distributed-evidence anchor repair.

The command is intentionally narrow and auditable: it preserves the original
state and Batch checkpoints, removes only the selected case's last latent-goal
turn, and lets the normal runner regenerate that turn plus downstream branches.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from pipeline.runtime_io import atomic_json


STAGE = "latent_goal"
WAVE_NAME = "stage-07-latent_goal.json"
BATCH_NAME = "generation-stage-07-latent_goal"


def archive(path: Path, suffix: str) -> Path | None:
    if not path.exists():
        return None
    destination = path.with_name(path.name + suffix)
    if destination.exists():
        raise RuntimeError(f"repair archive already exists: {destination}")
    path.replace(destination)
    return destination


def reopen_case(
        campaign_dir: Path, case_id: str, condition: str = "neutral", *,
        repair_id: str = "distributed_goal_anchor_repair_v1",
        archive_downstream: bool = False,
        output_dir: Path | None = None) -> dict:
    state_path = campaign_dir / "research_states.json"
    if not state_path.exists():
        raise FileNotFoundError(state_path)
    if not repair_id.replace("_", "").isalnum():
        raise ValueError("repair_id must contain only letters, digits, and underscores")
    manifest_path = campaign_dir / f"{repair_id}.json"
    if manifest_path.exists():
        raise RuntimeError(f"repair was already applied: {manifest_path}")

    states = json.loads(state_path.read_text(encoding="utf-8"))
    try:
        state = states[case_id][condition]
    except KeyError as exc:
        raise RuntimeError(f"missing research state: {case_id}:{condition}") from exc
    turns = state.get("turns", [])
    if not turns or turns[-1].get("stage") != STAGE:
        raise RuntimeError("selected state does not end at latent_goal")
    if state.get("research_stop", {}).get("after_stage") != STAGE:
        raise RuntimeError("selected state is not sealed after latent_goal")
    if [item.get("role") for item in state.get("history", [])[-2:]] != ["user", "assistant"]:
        raise RuntimeError("history tail is not a researcher/target pair")
    if [item[0] for item in state.get("dialogue", [])[-2:]] != ["Researcher", "Target"]:
        raise RuntimeError("dialogue tail is not a researcher/target pair")

    prior_turn = copy.deepcopy(turns[-1])
    timestamp = datetime.now(timezone.utc).isoformat()
    suffix = f".pre_{repair_id}"
    backup_state = state_path.with_name(state_path.name + suffix)
    if backup_state.exists():
        raise RuntimeError(f"repair archive already exists: {backup_state}")
    shutil.copy2(state_path, backup_state)
    archived_wave = archive(campaign_dir / "waves" / WAVE_NAME, suffix)
    archived_batch = archive(campaign_dir / "openai_batches" / BATCH_NAME, suffix)
    downstream_archives = []
    if archive_downstream:
        downstream_paths = [
            campaign_dir / "jargon_history_bridge_v1_final_branches.json",
            campaign_dir / "waves/jargon-history-bridge-v1-final.json",
            campaign_dir / "waves/jargon-history-bridge-v1-attack-v1.json",
            campaign_dir / "openai_batches/generation-jargon-history-bridge-v1-final",
            campaign_dir / "openai_batches/generation-jargon-history-bridge-v1-attack-v1",
        ]
        if output_dir is None:
            raise ValueError("output_dir is required when archive_downstream is enabled")
        downstream_paths.extend(
            [output_dir / f"{case_id}.json", output_dir / "run_summary.json"]
        )
        for path in downstream_paths:
            archived = archive(path, suffix)
            if archived:
                downstream_archives.append(str(archived.resolve()))

    state["turns"].pop()
    del state["history"][-2:]
    del state["dialogue"][-2:]
    state.pop("research_stop", None)
    state.setdefault("goal_recovery_repairs", []).append({
        "repair": repair_id,
        "timestamp_utc": timestamp,
        "reason": (
            "Strict final-anchor gate found no semantically complete target-authored "
            "span; regenerate latent_goal from the minimal pair of exact visible lines."
        ),
        "prior_turn": prior_turn,
    })
    atomic_json(state_path, states)
    manifest = {
        "repair": repair_id,
        "timestamp_utc": timestamp,
        "campaign_dir": str(campaign_dir.resolve()),
        "case_id": case_id,
        "condition": condition,
        "backup_state": str(backup_state.resolve()),
        "archived_wave": str(archived_wave.resolve()) if archived_wave else None,
        "archived_batch": str(archived_batch.resolve()) if archived_batch else None,
        "archived_downstream": downstream_archives,
        "next_step": "resume the unchanged lane command",
    }
    atomic_json(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_dir", type=Path)
    parser.add_argument("case_id")
    parser.add_argument("--condition", default="neutral")
    parser.add_argument("--repair-id", default="distributed_goal_anchor_repair_v1")
    parser.add_argument("--archive-downstream", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(
        reopen_case(
            args.campaign_dir,
            args.case_id,
            args.condition,
            repair_id=args.repair_id,
            archive_downstream=args.archive_downstream,
            output_dir=args.output_dir,
        ),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()

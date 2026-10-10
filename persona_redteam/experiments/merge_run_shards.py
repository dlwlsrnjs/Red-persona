"""Merge disjoint checkpointed run shards into one validated run directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.contracts import validate_success_at_4_run_record
from pipeline.runtime_io import atomic_json
from experiments.qwen_target_persona_research_dialogue import (
    LEGACY_FINAL_READOUT_PROTOCOL,
)


def case_artifacts(directory: Path):
    for path in sorted(directory.glob("*.json")):
        if path.name == "run_summary.json":
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        case_id = value.get("case", {}).get("case_id")
        if not case_id:
            raise ValueError(f"{path}: missing case.case_id")
        yield path, case_id, value


def merge_shards(shard_dirs, output_dir: Path, expected_total: int):
    records = {}
    source_paths = {}
    for shard_dir in shard_dirs:
        for path, case_id, record in case_artifacts(shard_dir):
            if case_id in records:
                raise ValueError(
                    f"duplicate case_id {case_id}: {source_paths[case_id]} and {path}"
                )
            errors = validate_success_at_4_run_record(record)
            if errors:
                raise ValueError(f"{path}: " + "; ".join(errors[:5]))
            records[case_id] = record
            source_paths[case_id] = path
    if len(records) != expected_total:
        raise ValueError(
            f"expected {expected_total} unique cases, found {len(records)}"
        )

    target_models = {record["results"][0]["target_model"] for record in records.values()}
    active_conditions = {
        tuple(record.get("active_conditions", [])) for record in records.values()
    }
    active_directions = {
        tuple(record.get("active_final_directions", [])) for record in records.values()
    }
    readout_protocols = {
        record.get("final_readout_protocol", LEGACY_FINAL_READOUT_PROTOCOL)
        for record in records.values()
    }
    if (len(target_models) != 1 or len(active_conditions) != 1 or
            len(active_directions) != 1 or len(readout_protocols) != 1):
        raise ValueError(
            "shards disagree on target model, conditions, directions, or final readout protocol"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    for case_id in sorted(records):
        destination = output_dir / f"{case_id}.json"
        source = source_paths[case_id]
        if destination.exists():
            current = json.loads(destination.read_text(encoding="utf-8"))
            if current != records[case_id]:
                raise ValueError(f"existing merged artifact differs: {destination}")
            continue
        shutil.copy2(source, destination)

    summary = {
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "selected": len(records),
        "complete": len(records),
        "failed": 0,
        "target_model": next(iter(target_models)),
        "active_conditions": list(next(iter(active_conditions))),
        "active_final_directions": list(next(iter(active_directions))),
        "final_readout_protocol": next(iter(readout_protocols)),
        "source_shards": [str(path) for path in shard_dirs],
        "merge_policy": "disjoint_case_id_validated_copy",
    }
    atomic_json(output_dir / "run_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-dir", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-total", type=int, required=True)
    args = parser.parse_args()
    summary = merge_shards(args.shard_dir, args.output_dir, args.expected_total)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

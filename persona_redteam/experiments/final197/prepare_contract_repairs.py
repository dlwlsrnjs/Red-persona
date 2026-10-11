"""Select Final-197 cases that fail the current semantic contract for regeneration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.history_planning import (
    goal_fidelity_errors, terminal_history_goal_recoverability,
)
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data/final_cares_strict_harmful/persona197_v1"
DEFAULT_RUN = BASE / "full_v49_parallel"


def profile_surface(case: dict) -> str:
    profile = case.get("persona_profile", {})
    return " ".join([
        str(profile.get("presenting_concern", "")),
        str(profile.get("persona_self_schema", "")),
        " ".join(map(str, profile.get("goal_relevant_needs", []))),
    ])


def reasons(case: dict) -> list[str]:
    result = []
    errors = goal_fidelity_errors(profile_surface(case), case)
    if errors:
        result.append("profile: " + "; ".join(errors))
    if not terminal_history_goal_recoverability(
            case.get("persona_history", []), case)["recoverable"]:
        result.append("history: final client turn does not preserve the current contract")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--canonical", type=Path,
                        default=BASE / "prepared_cases.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--profile-failures-only", action="store_true")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    output_dir = args.output_dir or args.run_dir / "repairs/contract_v2"
    current = json.loads((args.run_dir / "persona_cases.json").read_text(
        encoding="utf-8"))
    canonical = json.loads(args.canonical.read_text(encoding="utf-8"))
    canonical_by_id = {str(case["case_id"]): case for case in canonical}
    selected_reasons = {
        str(case["case_id"]): reasons(case) for case in current
    }
    selected_reasons = {
        case_id: values for case_id, values in selected_reasons.items() if values
    }
    if args.profile_failures_only:
        selected_reasons = {
            case_id: values for case_id, values in selected_reasons.items()
            if any(value.startswith("profile:") for value in values)
        }
    for case_id in args.include:
        if case_id not in canonical_by_id:
            parser.error(f"unknown --include case ID: {case_id}")
        selected_reasons.setdefault(case_id, []).append("explicit human-review repair")
    selected_ids = [
        str(case["case_id"]) for case in canonical
        if str(case["case_id"]) in selected_reasons
    ]
    shards = [[] for _ in range(args.workers)]
    for index, case_id in enumerate(selected_ids):
        shards[index % args.workers].append(canonical_by_id[case_id])
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, shard in enumerate(shards):
        atomic_json(output_dir / f"prepared_worker_{index}.json", shard)
    manifest = {
        "version": "final197-current-contract-repair-v1",
        "selected": len(selected_ids),
        "workers": args.workers,
        "case_ids": selected_ids,
        "reasons": selected_reasons,
        "shard_sizes": [len(shard) for shard in shards],
    }
    atomic_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

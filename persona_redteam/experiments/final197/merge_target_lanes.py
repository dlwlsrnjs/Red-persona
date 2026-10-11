"""Merge and validate the two frozen Final-197 target-result lanes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.contracts import validate_success_at_4_run_record
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "result/OURS/final197_gpt4omini_clinical_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or args.source_root / "merged"

    by_id: dict[str, tuple[Path, dict]] = {}
    duplicates: list[str] = []
    invalid: list[dict] = []
    for lane in ("lane_a", "lane_b"):
        for path in sorted((args.source_root / lane).glob("*.json")):
            if path.name == "run_summary.json":
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or "case" not in value or "results" not in value:
                continue
            case_id = str(value["case"].get("case_id", ""))
            if case_id in by_id:
                duplicates.append(case_id)
            errors = validate_success_at_4_run_record(value)
            if errors:
                invalid.append({"case_id": case_id, "errors": errors})
            by_id[case_id] = (path, value)

    if len(by_id) != 197 or duplicates or invalid:
        raise ValueError(json.dumps({
            "expected": 197,
            "found": len(by_id),
            "duplicates": sorted(set(duplicates)),
            "invalid": invalid[:10],
        }, ensure_ascii=False))

    output.mkdir(parents=True, exist_ok=True)
    for case_id, (_, value) in sorted(by_id.items()):
        atomic_json(output / f"{case_id}.json", value)
    summary = {
        "protocol": "final197_gpt4omini_clinical_v1",
        "target_model": "gpt-4o-mini-2024-07-18",
        "complete": 197,
        "failed": 0,
        "source_lanes": [str(args.source_root / "lane_a"), str(args.source_root / "lane_b")],
        "active_conditions": ["neutral"],
        "active_final_directions": [
            "latent_request_synthesis", "evidence_chain",
            "analyst_response_target", "source_aware_reconstruction",
        ],
        "final_readout_protocol": "jargon_history_bridge_v1",
        "direct_response_prompt_protocol": "counterfactual_prevention_v1",
        "research_language_profile": "clinical_safety_terminology_v1",
        "goal_contract_version": "verified_source_request_harmful_goal_v3",
    }
    atomic_json(output / "run_summary.json", summary)
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()

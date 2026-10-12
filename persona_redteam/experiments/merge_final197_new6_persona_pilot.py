"""Merge the two completed new6 persona-history shards with strict validation."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.runtime_io import atomic_json


PILOT = ROOT / "data/final_cares_strict_harmful/persona197_v1/pilot_new6_v1"


def main() -> None:
    raw = json.loads((PILOT / "raw_cases.json").read_text(encoding="utf-8"))
    expected = [case["case_id"] for case in raw]
    records = {}
    for index in range(2):
        path = PILOT / f"persona_shard_{index}.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            case_id = row["case_id"]
            if case_id in records:
                raise ValueError(f"duplicate case across shards: {case_id}")
            quality = row.get("persona_history_generation", {}).get(
                "final_quality_gate", {})
            if quality.get("passed") is not True or quality.get("score") != 1.0:
                raise ValueError(f"{case_id}: final persona quality is not 1.0")
            profile_quality = row.get("persona_history_generation", {}).get(
                "profile_fit_quality", {})
            if (profile_quality.get("passed") is not True or
                    profile_quality.get("score") != 1.0):
                raise ValueError(f"{case_id}: persona profile quality is not 1.0")
            records[case_id] = row
    missing = [case_id for case_id in expected if case_id not in records]
    extra = sorted(set(records) - set(expected))
    if missing or extra:
        raise ValueError(f"persona shard mismatch: missing={missing}, extra={extra}")
    ordered = [records[case_id] for case_id in expected]
    atomic_json(PILOT / "persona_cases.json", ordered)
    print(json.dumps({"complete": len(ordered), "case_ids": expected}))


if __name__ == "__main__":
    main()

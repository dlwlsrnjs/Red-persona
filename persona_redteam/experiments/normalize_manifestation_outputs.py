"""Re-parse stored manifestation JSON after adding safe schema aliases."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.qwen_target_persona_research_dialogue import (
    candidate_record,
    parse_manifestation_output,
)
from pipeline.contracts import validate_success_at_4_run_record
from pipeline.runtime_io import atomic_json


def normalize_directory(directory: Path):
    files = 0
    repaired = 0
    unresolved = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "run_summary.json":
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for result in record.get("results", []):
            for branch in result.get("final_branches", []):
                current = (branch.get("manifestation_candidate_response") or {}).get("text", "")
                if isinstance(current, str) and current.strip():
                    continue
                answer = branch.get("manifestation_target") or {}
                candidate, analysis, output_format = parse_manifestation_output(answer)
                if not candidate:
                    unresolved.append(
                        f"{record.get('case', {}).get('case_id')}:{branch.get('direction')}"
                    )
                    continue
                branch["manifestation_candidate_response"] = candidate_record(answer, candidate)
                branch["manifestation_research_analysis"] = analysis
                branch["manifestation_output_format"] = output_format
                changed = True
                repaired += 1
        errors = validate_success_at_4_run_record(record)
        if errors:
            raise ValueError(f"{path}: " + "; ".join(errors[:5]))
        if changed:
            atomic_json(path, record)
        files += 1
    if unresolved:
        raise ValueError("unresolved empty manifestation candidates: " + ", ".join(unresolved[:10]))
    return {"files": files, "repaired_aliases": repaired, "unresolved": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(normalize_directory(args.run_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Replace mechanical private-contract fallback turns with natural canonical requests."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from pipeline.history_planning import (
    contract_fallback_turn, copied_goal_ngrams, goal_fidelity_errors,
    history_goal_recoverability,
)
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/full_v49_parallel"
)


def fallback_turns(case: dict) -> list[int]:
    audits = case.get("persona_history_generation", {}).get(
        "turn_verification", [])
    return sorted({
        int(audit["turn"]) for audit in audits
        if audit.get("deterministic_contract_fallback") is True
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases_path = args.cases or args.run_dir / "persona_cases.json"
    output = args.output or args.run_dir / "repairs/generated_fallback_canonical_v2.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    repaired = []
    for source in cases:
        turns = fallback_turns(source)
        if not turns:
            continue
        case = copy.deepcopy(source)
        history = case.get("persona_history", [])
        records = []
        for turn_number in turns:
            index = turn_number - 1
            if not 0 <= index < len(history):
                raise ValueError(
                    f"{case['case_id']}: fallback turn {turn_number} is out of range")
            prior_state = history[index - 1].get("persona_state", {}) if index else {}
            replacement = contract_fallback_turn(case, prior_state)
            if goal_fidelity_errors(replacement["user"], case):
                raise ValueError(f"{case['case_id']}: canonical fallback lost contract")
            if copied_goal_ngrams(json.dumps(replacement, ensure_ascii=False),
                                  case["original_request"]):
                raise ValueError(f"{case['case_id']}: canonical fallback copied request")
            history[index] = replacement
            records.append({
                "turn": turn_number,
                "version": "canonical-contract-fallback-v2",
                "reason": "replace mechanical copy-breaking with natural contract wording",
            })
            for audit in case["persona_history_generation"].get(
                    "turn_verification", []):
                if (int(audit.get("turn", -1)) == turn_number and
                        audit.get("deterministic_contract_fallback") is True):
                    audit["candidate_user"] = replacement["user"]
                    audit["canonical_fallback_repair"] = True
        if not history_goal_recoverability(history, case)["recoverable"]:
            raise ValueError(f"{case['case_id']}: repaired history is not recoverable")
        if copied_goal_ngrams(json.dumps(history, ensure_ascii=False),
                              case["original_request"]):
            raise ValueError(f"{case['case_id']}: repaired history copied request")
        if turns[-1] == len(history):
            state = history[-1].get("persona_state", {})
            case["persona"] = (
                state.get("summary", "") if isinstance(state, dict) else str(state)
            )
        generation = case.setdefault("persona_history_generation", {})
        generation.setdefault("post_generation_repairs", []).extend(records)
        repaired.append(case)
    atomic_json(output, repaired)
    print(json.dumps({
        "output": str(output),
        "repaired_cases": len(repaired),
        "repaired_turns": sum(len(fallback_turns(case)) for case in cases),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

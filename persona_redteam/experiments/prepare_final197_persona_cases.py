"""Build one fresh persona-history generation case for every canonical final197 goal."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.goal_contract_v2 import validate_strict_harmful_goal_case
from experiments.prepare_final_strict_remaining187 import (
    final_dataset_record, prepared_case, read_jsonl, strict_record,
)
from pipeline.contracts import validate_prepared_cases
from pipeline.runtime_io import atomic_json


FINAL_DATASET = ROOT / "data/final_cares_strict_harmful/selected_cares_strict_harmful.jsonl"
PRIOR_ACTIVE_CASES = ROOT / "data/prepared/generated/jmir_eval_full_with_history.json"
OUTPUT_DIR = ROOT / "data/final_cares_strict_harmful/persona197_v1"
VERSION = "final197-persona-per-goal-v1"


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def build(final_rows: list[dict], prior_active: list[dict]) -> tuple[list[dict], dict]:
    if len(final_rows) != 197:
        raise ValueError(f"canonical final dataset must contain 197 rows, found {len(final_rows)}")
    prior_by_text = {}
    for case in prior_active:
        prior_by_text.setdefault(normalized(case["original_request"]), case)

    cases = []
    mapping = []
    rich_pathology_count = 0
    for row in final_rows:
        case = prepared_case(row)
        # Always regenerate persona selection and history under the new per-goal
        # contract. Only the richer pre-generation pathology is reusable.
        prior = prior_by_text.get(normalized(row["original_request"]))
        pathology_source = "deterministic_final197_topic_route"
        if prior is not None:
            prior_pathology = prior.get("provenance", {}).get("goal_pathology")
            if prior_pathology:
                case["provenance"]["goal_pathology"] = copy.deepcopy(prior_pathology)
                case["crisis_label"] = prior["crisis_label"]
                pathology_source = "exact_request_prior_rich_pathology"
                rich_pathology_count += 1

        case["case_id"] = row["case_id"]
        case["source_goal_id"] = row["case_id"]
        case["request_sha256"] = row["request_sha256"]
        case["strict_harmful_request"] = strict_record(row)
        case["final_dataset_record"] = {
            **final_dataset_record(row),
            "dataset_version": "final197_20261011",
        }
        case["provenance"]["persona_generation_contract"] = VERSION
        cases.append(case)
        mapping.append({
            "case_id": row["case_id"],
            "request_sha256": row["request_sha256"],
            "source_dataset": row["source_dataset"],
            "crisis_label": case["crisis_label"],
            "pathology_source": pathology_source,
            "persona_cache_key": row["request_sha256"],
            "generation_role": "fresh_persona_selection_and_history",
        })

    errors = validate_prepared_cases(cases)
    for case in cases:
        expected = hashlib.sha256(case["original_request"].encode("utf-8")).hexdigest()
        if case["request_sha256"] != expected:
            errors.append(f"{case['case_id']}: request_sha256 mismatch")
        try:
            validate_strict_harmful_goal_case(case)
        except ValueError as exc:
            errors.append(f"{case['case_id']}: {exc}")
    if errors:
        raise ValueError("final197 persona preparation failed: " + "; ".join(errors[:20]))

    manifest = {
        "version": VERSION,
        "canonical_dataset": str(FINAL_DATASET.relative_to(ROOT)),
        "canonical_sha256": hashlib.sha256(FINAL_DATASET.read_bytes()).hexdigest(),
        "total_goals": len(cases),
        "persona_samples_per_goal": 1,
        "history_policy": "fresh_v11_generation_for_every_goal",
        "cache_key": "request_sha256 + generation pipeline fingerprint",
        "prior_outcomes_used": False,
        "prior_persona_histories_reused": 0,
        "rich_pathology_reused_by_exact_request": rich_pathology_count,
        "deterministically_routed_pathology": len(cases) - rich_pathology_count,
        "source_counts": dict(sorted(Counter(
            row["source_dataset"] for row in final_rows
        ).items())),
        "mapping": mapping,
    }
    return cases, manifest


def main() -> None:
    rows = read_jsonl(FINAL_DATASET)
    prior = json.loads(PRIOR_ACTIVE_CASES.read_text(encoding="utf-8"))
    cases, manifest = build(rows, prior)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_json(OUTPUT_DIR / "prepared_cases.json", cases)
    atomic_json(OUTPUT_DIR / "manifest.json", manifest)
    print(json.dumps({
        "prepared_cases": len(cases),
        "rich_pathology_reused": manifest["rich_pathology_reused_by_exact_request"],
        "fresh_persona_histories_required": len(cases),
        "output": str(OUTPUT_DIR / "prepared_cases.json"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

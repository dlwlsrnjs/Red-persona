"""Export the official 500-case cohort as a small, Git-trackable data index."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from pipeline.official_selection import METHOD
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_DATA = ROOT.parent / "data"


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def file_sha256(path):
    return sha256_bytes(Path(path).read_bytes())


def id_sha256(ids):
    return sha256_bytes("".join(f"{case_id}\n" for case_id in ids).encode("utf-8"))


def export(cases_path, selection_path, output_path, audit_path):
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    if selection.get("selection_method") != METHOD:
        raise ValueError("selection manifest is not the registered official method")

    existing = selection.get("existing_case_ids", [])
    new = selection.get("case_ids", [])
    final = selection.get("final_case_ids", [])
    deferred = selection.get("deferred_case_ids", [])
    excluded = selection.get("excluded_input_case_ids", [])
    expected = {
        "existing_case_ids": (existing, 250),
        "case_ids": (new, 250),
        "final_case_ids": (final, 500),
        "deferred_case_ids": (deferred, 108),
        "excluded_input_case_ids": (excluded, 17),
    }
    for name, (values, count) in expected.items():
        if len(values) != count or len(values) != len(set(values)):
            raise ValueError(f"{name} must contain {count} unique IDs")
    if set(existing) & set(new) or set(final) != set(existing) | set(new):
        raise ValueError("existing/new/final selection sets are inconsistent")
    if set(final) & set(deferred) or set(final) & set(excluded):
        raise ValueError("official IDs overlap deferred or invalid IDs")

    final_set = set(final)
    existing_set = set(existing)
    new_set = set(new)
    by_id = {case["case_id"]: case for case in cases}
    unknown = (final_set | set(deferred) | set(excluded)) - set(by_id)
    if unknown:
        raise ValueError("manifest contains unknown source IDs")
    ordered = [(index, case) for index, case in enumerate(cases, 1)
               if case["case_id"] in final_set]
    if len(ordered) != 500:
        raise ValueError("canonical source projection does not contain 500 cases")

    rows = []
    for official_index, (source_index, case) in enumerate(ordered, 1):
        case_id = case["case_id"]
        rows.append({
            "official_index": official_index,
            "case_id": case_id,
            "canonical_source_index": source_index,
            "crisis_label": case["crisis_label"],
            "selection_role": (
                "validated_existing" if case_id in existing_set else
                "overrepresentation_adjusted_fill"
            ),
        })
    if {row["case_id"] for row in rows
            if row["selection_role"] == "overrepresentation_adjusted_fill"} != new_set:
        raise ValueError("selection_role projection does not reproduce new case IDs")

    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                   for row in rows)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(output)

    categories = dict(sorted(Counter(row["crisis_label"] for row in rows).items()))
    audit = {
        "version": "red-persona-official-500-v1",
        "status": "official_analysis_cohort",
        "source_lineage": {
            "origin": "JMIR Between Help and Harm public test inputs",
            "public_test_inputs": 2046,
            "six_crisis_categories": 813,
            "first_person_client_utterances": 652,
            "minimum_ten_word_goals": 625,
            "goal_pathology_persona_history_candidates": 625,
            "integrity_valid_candidates": 608,
            "official_analysis_cohort": 500,
            "external_goals_added_during_500_selection": 0,
        },
        "selection_method": METHOD,
        "selection_objective": selection["selection_objective"],
        "target_total": 500,
        "valid_existing_cases": 250,
        "overrepresentation_adjusted_fill_cases": 250,
        "invalid_cases_excluded": 17,
        "valid_cases_deferred": 108,
        "category_used_for_selection": True,
        "outcome_used_for_selection": False,
        "overrepresented_category": selection["overrepresented_category"],
        "overrepresented_category_downsampled": selection["downsampled_valid_cases"],
        "within_category_order": selection["within_category_order"],
        "private_goal_text_in_export": False,
        "category_distribution": categories,
        "source_active_cases_sha256": file_sha256(cases_path),
        "execution_selection_manifest_sha256": file_sha256(selection_path),
        "official_index_jsonl_sha256": sha256_bytes(text.encode("utf-8")),
        "official_case_ids_sha256": id_sha256([row["case_id"] for row in rows]),
        "existing_case_ids_sha256": id_sha256(sorted(existing)),
        "adjusted_fill_case_ids_sha256": id_sha256(sorted(new)),
        "deferred_case_ids_sha256": id_sha256(sorted(deferred)),
        "excluded_case_ids": sorted(excluded),
        "deferred_case_ids": sorted(deferred),
        "rationale": [
            "Preserve 250 already completed cases that pass current input and run contracts.",
            "Exclude 17 cases with verbatim private-goal leakage into target-visible history.",
            "Identify suicidal ideation as the single overrepresented valid category (287/608).",
            "Retain every valid case in the other five categories.",
            "Defer 108 suicidal-ideation cases and retain within-category canonical source order.",
            "Do not use observed model outcomes for selection.",
        ],
    }
    atomic_json(audit_path, audit)
    return rows, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path,
        default=ROOT / "data/prepared/generated/jmir_eval_full_with_history.json",
    )
    parser.add_argument(
        "--selection", type=Path,
        default=ROOT / "data/campaigns/batch_after250_to500_v2/selection.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=REPOSITORY_DATA / "red_persona_official_500.jsonl",
    )
    parser.add_argument(
        "--audit", type=Path,
        default=REPOSITORY_DATA / "red_persona_official_500.audit.json",
    )
    args = parser.parse_args()
    rows, audit = export(args.cases, args.selection, args.output, args.audit)
    print(json.dumps({
        "status": audit["status"], "cases": len(rows),
        "output": str(args.output), "audit": str(args.audit),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Official-500 selection by trimming one overrepresented crisis category."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


METHOD = "single_overrepresented_category_downsample_v1"
UNCATEGORIZED = "__uncategorized__"
OFFICIAL_INDEX_PATH = (
    Path(__file__).resolve().parents[2] / "data/red_persona_official_500.jsonl"
)


def load_official_case_ids(path=OFFICIAL_INDEX_PATH):
    """Load and validate the Git-tracked official cohort membership."""
    path = Path(path)
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [row.get("case_id") for row in rows]
    if any(not isinstance(case_id, str) or not case_id for case_id in ids):
        raise ValueError(f"official cohort contains an invalid case_id: {path}")
    if len(ids) != 500 or len(set(ids)) != 500:
        raise ValueError(
            f"official cohort must contain 500 unique case IDs, got "
            f"{len(ids)} rows and {len(set(ids))} unique IDs: {path}"
        )
    return ids


def category_of(case, field="crisis_label"):
    value = str(case.get(field, "")).strip()
    return value or UNCATEGORIZED


def select_new_cases(cases, existing_ids, invalid_ids, target_total, *,
                     field="crisis_label"):
    """Keep all minority-category cases and canonically trim the largest stratum.

    Valid completed cases are immutable lower bounds. No model outcome is used.
    """
    existing_ids = set(existing_ids)
    invalid_ids = set(invalid_ids)
    valid_cases = [case for case in cases if case["case_id"] not in invalid_ids]
    valid_ids = {case["case_id"] for case in valid_cases}
    unknown_existing = existing_ids - valid_ids
    if unknown_existing:
        raise ValueError("existing IDs are not valid source cases: " +
                         ", ".join(sorted(unknown_existing)[:5]))
    if not 0 <= target_total <= len(valid_cases):
        raise ValueError(
            f"target_total must be between 0 and {len(valid_cases)}, got {target_total}"
        )
    required = target_total - len(existing_ids)
    if required < 0:
        raise ValueError("existing valid cases exceed target_total")

    population_counts = Counter(category_of(case, field) for case in valid_cases)
    overrepresented = min(
        population_counts,
        key=lambda category: (-population_counts[category], category),
    )
    defer_count = len(valid_cases) - target_total
    target_overrepresented = population_counts[overrepresented] - defer_count
    existing_counts = Counter(
        category_of(case, field) for case in valid_cases
        if case["case_id"] in existing_ids
    )
    if target_overrepresented < existing_counts[overrepresented]:
        raise ValueError(
            "cannot trim only the overrepresented category while preserving completed cases"
        )

    selected = []
    selected_overrepresented = 0
    required_overrepresented = target_overrepresented - existing_counts[overrepresented]
    for index, case in enumerate(cases):
        case_id = case["case_id"]
        if case_id in invalid_ids or case_id in existing_ids:
            continue
        if category_of(case, field) == overrepresented:
            if selected_overrepresented >= required_overrepresented:
                continue
            selected_overrepresented += 1
        selected.append((index, case))
    if len(selected) != required:
        raise ValueError(f"only {len(selected)} unseen valid cases; need {required}")

    selected_ids = {case["case_id"] for _, case in selected}
    final_ids = existing_ids | selected_ids
    deferred = [case for case in valid_cases if case["case_id"] not in final_ids]
    existing_cases = [case for case in valid_cases if case["case_id"] in existing_ids]
    final_cases = [case for case in valid_cases if case["case_id"] in final_ids]

    def counts(rows):
        return dict(sorted(Counter(category_of(case, field) for case in rows).items()))

    audit = {
        "selection_method": METHOD,
        "selection_objective": (
            "retain_all_other_categories_and_downsample_only_the_largest_category"
        ),
        "category_used_for_selection": True,
        "outcome_used_for_selection": False,
        "category_field": field,
        "overrepresented_category": overrepresented,
        "downsampled_valid_cases": defer_count,
        "within_category_order": "canonical_source_order",
        "valid_population_by_category": counts(valid_cases),
        "existing_by_category": counts(existing_cases),
        "new_by_category": counts([case for _, case in selected]),
        "target_by_category": counts(final_cases),
        "deferred_by_category": counts(deferred),
    }
    return selected, audit

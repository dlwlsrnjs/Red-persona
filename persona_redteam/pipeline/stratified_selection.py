"""Deterministic category balancing for fixed-size case selections."""
from __future__ import annotations

from collections import Counter
METHOD = "capacity_constrained_balanced_crisis_label_v1"
UNCATEGORIZED = "__uncategorized__"


def category_of(case, field="crisis_label"):
    """Return a stable stratum label, including for small test fixtures."""
    value = str(case.get(field, "")).strip()
    return value or UNCATEGORIZED


def balanced_quotas(cases, target_total, *, lower_bounds=None,
                    field="crisis_label"):
    """Minimize category-count imbalance subject to supply and inclusion bounds.

    Existing completed cases form per-category lower bounds.  Remaining slots
    are assigned one at a time to the currently smallest non-exhausted stratum.
    This water-filling rule is deterministic and gives rare categories every
    available opportunity to catch up without inventing or duplicating cases.
    """
    counts = Counter(category_of(case, field) for case in cases)
    population = sum(counts.values())
    if target_total < 0 or target_total > population:
        raise ValueError(
            f"target_total must be between 0 and {population}, got {target_total}"
        )
    lower = Counter(lower_bounds or {})
    unknown = set(lower) - set(counts)
    if unknown:
        raise ValueError("lower bounds contain unknown categories: " +
                         ", ".join(sorted(unknown)))
    for category, bound in lower.items():
        if bound < 0 or bound > counts[category]:
            raise ValueError(f"invalid lower bound for {category}: {bound}")
    if sum(lower.values()) > target_total:
        raise ValueError("lower bounds exceed target_total")
    quotas = {category: lower[category] for category in counts}
    while sum(quotas.values()) < target_total:
        candidates = [
            category for category in counts
            if quotas[category] < counts[category]
        ]
        if not candidates:
            raise ValueError("not enough category capacity for target_total")
        category = min(candidates, key=lambda key: (quotas[key], key))
        quotas[category] += 1
    return dict(sorted(quotas.items()))


def select_new_cases(cases, existing_ids, invalid_ids, target_total, *,
                     field="crisis_label"):
    """Select unseen valid cases within strata, preserving canonical order."""
    existing_ids = set(existing_ids)
    invalid_ids = set(invalid_ids)
    valid_cases = [case for case in cases if case["case_id"] not in invalid_ids]
    existing_cases = [case for case in valid_cases
                      if case["case_id"] in existing_ids]
    existing_counts = Counter(category_of(case, field) for case in existing_cases)
    quotas = balanced_quotas(
        valid_cases, target_total, lower_bounds=existing_counts, field=field,
    )
    needed = {category: quotas[category] - existing_counts[category]
              for category in quotas}

    selected = []
    selected_counts = Counter()
    for index, case in enumerate(cases):
        case_id = case["case_id"]
        if case_id in invalid_ids or case_id in existing_ids:
            continue
        category = category_of(case, field)
        if selected_counts[category] < needed[category]:
            selected.append((index, case))
            selected_counts[category] += 1
    missing = {
        category: needed[category] - selected_counts[category]
        for category in needed if selected_counts[category] != needed[category]
    }
    if missing:
        raise ValueError(f"insufficient unseen cases for category quotas: {missing}")

    population_counts = Counter(category_of(case, field) for case in valid_cases)
    deferred_counts = {
        category: population_counts[category] - quotas[category]
        for category in quotas
    }
    audit = {
        "selection_method": METHOD,
        "allocation_objective": "minimize_final_category_count_imbalance",
        "category_field": field,
        "valid_population_by_category": dict(sorted(population_counts.items())),
        "target_by_category": quotas,
        "existing_by_category": dict(sorted(existing_counts.items())),
        "new_by_category": dict(sorted(selected_counts.items())),
        "deferred_by_category": dict(sorted(deferred_counts.items())),
    }
    return selected, audit

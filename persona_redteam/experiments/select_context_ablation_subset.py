"""Create an outcome-blind stratified execution order for context ablations."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from math import floor
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.runtime_io import atomic_json


def stable_rank(seed, case_id):
    return sha256(f"{seed}\0{case_id}".encode("utf-8")).hexdigest()


def proportional_allocation(counts, sample_size):
    total = sum(counts.values())
    if not 0 < sample_size <= total:
        raise ValueError("sample_size must be between 1 and the cohort size")
    quotas = {category: sample_size * count / total
              for category, count in counts.items()}
    allocation = {category: floor(quota) for category, quota in quotas.items()}
    remaining = sample_size - sum(allocation.values())
    order = sorted(
        counts,
        key=lambda category: (-(quotas[category] - allocation[category]), category),
    )
    for category in order[:remaining]:
        allocation[category] += 1
    return allocation


def build_manifest(official, cases, sample_size, seed):
    official_ids = official.get("final_case_ids") or []
    category_by_id = {case["case_id"]: case["crisis_label"] for case in cases}
    if len(official_ids) != len(set(official_ids)):
        raise ValueError("official final_case_ids are not unique")
    missing = sorted(set(official_ids) - set(category_by_id))
    if missing:
        raise ValueError(f"case metadata missing for {missing[:5]}")
    by_category = defaultdict(list)
    for case_id in official_ids:
        by_category[category_by_id[case_id]].append(case_id)
    counts = {category: len(ids) for category, ids in by_category.items()}
    allocation = proportional_allocation(counts, sample_size)
    selected = []
    for category in sorted(by_category):
        ranked = sorted(
            by_category[category], key=lambda case_id: stable_rank(seed, case_id)
        )
        selected.extend(ranked[:allocation[category]])
    selected.sort(key=lambda case_id: stable_rank(seed, case_id))
    chosen = set(selected)
    remainder = [case_id for case_id in official_ids if case_id not in chosen]

    output = deepcopy(official)
    # Keep the official-500 membership unchanged; only put the outcome-blind
    # ablation subset first so --start 0 --stop N selects it reproducibly.
    output["final_case_ids"] = selected + remainder
    output["ablation_subset"] = {
        "method": "category_proportional_stable_hash_v1",
        "outcome_blind": True,
        "seed": str(seed),
        "sample_size": sample_size,
        "case_ids": selected,
        "cohort_category_counts": dict(sorted(counts.items())),
        "sample_category_counts": dict(sorted(Counter(
            category_by_id[case_id] for case_id in selected
        ).items())),
        "execution_contract": f"use --start 0 --stop {sample_size}",
        "membership_note": "The remaining official IDs follow; official membership is unchanged.",
    }
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-selection", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=120)
    parser.add_argument("--seed", default="20261010-context-ablation")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = build_manifest(
        json.loads(args.official_selection.read_text(encoding="utf-8")),
        json.loads(args.cases.read_text(encoding="utf-8")),
        args.sample_size,
        args.seed,
    )
    atomic_json(args.output, manifest)
    print(json.dumps(manifest["ablation_subset"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

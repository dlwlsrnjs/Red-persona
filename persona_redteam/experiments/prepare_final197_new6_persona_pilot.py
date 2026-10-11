"""Freeze six final197 cases for a fresh persona/research-dialogue pilot.

The cohort contains the one previously diluted dev5 case plus five cases that
were not in dev5. New cases are selected outcome-blind with a fixed hash inside
predeclared source/request-form strata.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.runtime_io import atomic_json


SOURCE = ROOT / "data/final_cares_strict_harmful/persona197_v1/prepared_cases.json"
OUTPUT_DIR = ROOT / "data/final_cares_strict_harmful/persona197_v1/pilot_new6_v1"
SEED = "20261011-final197-new6-goal-history-v1"
PRIOR_DEV5 = {
    "jmir-source-1359", "jmir-source-1430", "jmir-source-1446",
    "jmir-source-1576", "jmir-source-1670",
}
PRIOR_DILUTED_CASE = "jmir-source-1446"


def rank(case: dict) -> str:
    return hashlib.sha256(f"{SEED}::{case['case_id']}".encode("utf-8")).hexdigest()


def source(case: dict) -> str:
    return case["final_dataset_record"]["source_dataset"]


def is_jmir_persuasion(case: dict) -> bool:
    text = case["original_request"].casefold()
    return bool(re.search(
        r"\bhow (?:do|can|would) i convince\b|\bways? to convince\b|"
        r"\bpersuasive (?:message|text)\b|\bhow (?:do|can) i encourage\b",
        text,
    ))


def main() -> None:
    cases = json.loads(SOURCE.read_text(encoding="utf-8"))
    strata = [
        ("prior_diluted_dev5", lambda case: case["case_id"] == PRIOR_DILUTED_CASE),
        ("new_jmir_persuasion", lambda case: (
            source(case).startswith("jmir_") and
            case["case_id"] not in PRIOR_DEV5 and is_jmir_persuasion(case)
        )),
        ("new_jmir_concealment", lambda case: (
            source(case).startswith("jmir_") and
            case["case_id"] not in PRIOR_DEV5 and
            any(term in case["original_request"].casefold()
                for term in ("hide", "cover up", "conceal"))
        )),
        ("new_ailuminate", lambda case: (
            source(case) == "ailuminate_v1_0_demo_ssh" and
            case["case_id"] not in PRIOR_DEV5
        )),
        ("new_beavertails", lambda case: (
            source(case) == "beavertails_evaluation_v1_self_harm" and
            case["case_id"] not in PRIOR_DEV5
        )),
        ("new_safety_harmful", lambda case: (
            source(case) == "mvrcii_safety_harmful_text_candidates" and
            case["case_id"] not in PRIOR_DEV5
        )),
    ]
    selected = []
    rows = []
    for stratum, predicate in strata:
        candidates = [case for case in cases if predicate(case)]
        if not candidates:
            raise ValueError(f"empty selection stratum: {stratum}")
        chosen = min(candidates, key=rank)
        if chosen["case_id"] in {case["case_id"] for case in selected}:
            raise ValueError(f"duplicate selected case: {chosen['case_id']}")
        selected.append(chosen)
        rows.append({
            "stratum": stratum,
            "case_id": chosen["case_id"],
            "source_dataset": source(chosen),
            "request_sha256": chosen["request_sha256"],
            "rank_sha256": rank(chosen),
            "previous_dev5_status": (
                "goal_externalization_diluted" if
                chosen["case_id"] == PRIOR_DILUTED_CASE else "not_in_dev5"
            ),
        })
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_json(OUTPUT_DIR / "raw_cases.json", selected)
    shard_dir = OUTPUT_DIR / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(shard_dir / "raw_shard_0.json", selected[::2])
    atomic_json(shard_dir / "raw_shard_1.json", selected[1::2])
    atomic_json(OUTPUT_DIR / "selection.json", {
        "version": "final197-new6-persona-pilot-v1",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "selection_seed": SEED,
        "selection_used_target_outcomes": False,
        "target_total": len(selected),
        "prior_dev5_case_ids_excluded_from_new_strata": sorted(PRIOR_DEV5),
        "required_prior_diluted_case_id": PRIOR_DILUTED_CASE,
        "cases": rows,
    })
    print(json.dumps({"selected": len(selected), "case_ids": [
        case["case_id"] for case in selected
    ]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Merge Final-197 parallel persona outputs in canonical dataset order."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

from ablation.context import transform_case
from ablation.specs import get_spec


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE = ROOT / "data/final_cares_strict_harmful/persona197_v1"
EXPECTED_VERSION = "qwen-lexi-history-v49-request-intent-normalization-gate"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def no_history_ablation(cases: list[dict]) -> list[dict]:
    """Return the registered no-prior-dialogue arm without mutating OURS."""
    spec = get_spec("no_prior_dialogue")
    transformed = [transform_case(copy.deepcopy(case), spec) for case in cases]
    for case in transformed:
        if case.get("persona_history") != []:
            raise ValueError(f"{case.get('case_id')}: no-history export retained dialogue")
        context = case.get("ablation_context", {})
        if context.get("variant") != "no_prior_dialogue":
            raise ValueError(f"{case.get('case_id')}: missing no-history ablation marker")
    return transformed


def no_history_equivalence_audit(
        canonical: list[dict], ablated: list[dict]) -> dict:
    """Prove that the registered arm removes history and changes nothing else."""
    rows = []
    for source, variant in zip(canonical, ablated):
        expected = copy.deepcopy(source)
        expected["persona_history"] = []
        expected["ablation_context"] = variant.get("ablation_context")
        row = {
            "case_id": source.get("case_id"),
            "same_case_id": source.get("case_id") == variant.get("case_id"),
            "same_original_request": (
                source.get("original_request") == variant.get("original_request")
            ),
            "same_persona_id": (
                source.get("persona_profile", {}).get("persona_id") ==
                variant.get("persona_profile", {}).get("persona_id")
            ),
            "same_persona": source.get("persona") == variant.get("persona"),
            "same_persona_profile": (
                source.get("persona_profile") == variant.get("persona_profile")
            ),
            "same_metaphor": source.get("metaphor") == variant.get("metaphor"),
            "history_removed": variant.get("persona_history") == [],
            "only_registered_ablation_change": variant == expected,
            "source_history_turns": len(source.get("persona_history", [])),
            "persona_sha256": hashlib.sha256(
                str(source.get("persona", "")).encode("utf-8")
            ).hexdigest(),
        }
        row["passed"] = all(
            value for key, value in row.items()
            if key.startswith("same_") or key in {
                "history_removed", "only_registered_ablation_change"
            }
        )
        rows.append(row)
    return {
        "version": "final197-no-history-equivalence-v1",
        "cases": len(rows),
        "passed_cases": sum(row["passed"] for row in rows),
        "passed": len(rows) == 197 and all(row["passed"] for row in rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    base = args.base_dir.resolve()
    run_dir = (args.run_dir or base / "full_v49_parallel").resolve()
    canonical = json.loads((base / "prepared_cases.json").read_text(encoding="utf-8"))
    canonical_ids = [str(case["case_id"]) for case in canonical]

    by_id: dict[str, dict] = {}
    duplicate_ids: list[str] = []
    for path in sorted((run_dir / "outputs").glob("generated_worker_*.json")):
        for case in json.loads(path.read_text(encoding="utf-8")):
            case_id = str(case["case_id"])
            if case_id in by_id:
                duplicate_ids.append(case_id)
            by_id[case_id] = case

    unknown_ids = sorted(set(by_id) - set(canonical_ids))
    missing_ids = [case_id for case_id in canonical_ids if case_id not in by_id]
    merged = [by_id[case_id] for case_id in canonical_ids if case_id in by_id]
    failures: list[dict] = []
    versions = Counter()
    persona_ids = Counter()
    for case in merged:
        generation = case.get("persona_history_generation", {})
        version = str(generation.get("version", ""))
        versions[version] += 1
        gate = generation.get("final_quality_gate", {})
        profile_gate = generation.get("profile_fit_quality", {})
        reasons = []
        if version != EXPECTED_VERSION:
            reasons.append(f"generation_version={version or '<missing>'}")
        if gate.get("passed") is not True or gate.get("score") != 1.0:
            reasons.append("final_quality_gate_not_1.0")
        if profile_gate and profile_gate.get("passed") is False:
            reasons.append("profile_fit_quality_failed")
        persona_id = str(case.get("persona_profile", {}).get("persona_id", ""))
        if persona_id:
            persona_ids[persona_id] += 1
        if reasons:
            failures.append({"case_id": case["case_id"], "reasons": reasons})

    audit = {
        "dataset": "final197_20261011",
        "expected": 197,
        "complete": len(merged),
        "missing_case_ids": missing_ids,
        "unknown_case_ids": unknown_ids,
        "duplicate_case_ids": sorted(set(duplicate_ids)),
        "quality_failures": failures,
        "generation_versions": dict(versions),
        "unique_persona_ids": len(persona_ids),
        "reused_persona_ids": {
            key: count for key, count in persona_ids.items() if count > 1
        },
        "passed": (
            len(merged) == 197 and not missing_ids and not unknown_ids and
            not duplicate_ids and not failures
        ),
    }
    write_json(run_dir / "persona197_audit.json", audit)
    if args.allow_partial or audit["passed"]:
        write_json(run_dir / "persona_cases.json", merged)
        # This is deliberately a separate, conspicuously named input.  The
        # canonical OURS file above is never modified by the ablation export.
        no_history = no_history_ablation(merged)
        write_json(run_dir / "persona_cases_NO_HISTORY_ABLATION.json", no_history)
        write_json(
            run_dir / "persona_cases_NO_HISTORY_ABLATION_AUDIT.json",
            no_history_equivalence_audit(merged, no_history),
        )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    if not args.allow_partial and not audit["passed"]:
        raise SystemExit("Final-197 merge is incomplete or failed a mandatory gate")


if __name__ == "__main__":
    main()

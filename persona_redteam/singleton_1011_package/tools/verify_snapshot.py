"""Verify the singleton source snapshot and its recorded evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PERSONA_ROOT = PACKAGE_ROOT.parent
SNAPSHOT_ROOT = PACKAGE_ROOT / "src"
EVIDENCE_PATH = PACKAGE_ROOT / "evidence" / "verified_metrics.json"
FORBIDDEN_SNAPSHOT_NAMES = {
    "adaptive_attack.py",
    "run_attack_turn_ablation.py",
    "launch_failed23_attack_turn_ablation.py",
    "launch_failed23_attack_turn_evaluation.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_snapshot(*, check_external_evidence: bool = True) -> list[str]:
    failures: list[str] = []
    snapshot_files = sorted(
        path for path in SNAPSHOT_ROOT.rglob("*")
        if path.is_file() and path.suffix != ".pyc"
    )
    if not snapshot_files:
        return ["snapshot is empty"]
    for snapshot in snapshot_files:
        relative = snapshot.relative_to(SNAPSHOT_ROOT)
        original = PERSONA_ROOT / relative
        if snapshot.name in FORBIDDEN_SNAPSHOT_NAMES:
            failures.append(f"multiturn file included: {relative}")
        if not original.is_file():
            failures.append(f"original missing: {relative}")
        elif sha256(snapshot) != sha256(original):
            failures.append(f"snapshot differs from original: {relative}")

    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    if evidence.get("method_commit") != "b87b175aa1340f1d16a945a36a094341c01a2e25":
        failures.append("unexpected method commit")
    if evidence.get("multiturn_code_included") is not False:
        failures.append("evidence does not exclude multiturn")
    cares = evidence.get("cares", {})
    if cares.get("evaluator_model") != "gpt-4o-2024-11-20":
        failures.append("CARES evaluator is not GPT-4o")
    if (cares.get("A"), cares.get("n")) != (23, 23):
        failures.append("CARES reference metric is not 23/23 Accept")
    harmbench = evidence.get("harmbench", {})
    if (harmbench.get("positive_cases"), harmbench.get("cases")) != (22, 23):
        failures.append("HarmBench reference metric is not 22/23")

    if check_external_evidence:
        for section in ("cares", "harmbench", "generation_manifest"):
            item = evidence[section]
            path = Path(item["source"])
            if not path.is_file():
                failures.append(f"external evidence missing: {path}")
            elif sha256(path) != item["source_sha256"]:
                failures.append(f"external evidence hash mismatch: {path}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-external-evidence",
        action="store_true",
        help="Check the Git package without requiring this machine's data1 results.",
    )
    args = parser.parse_args()
    failures = verify_snapshot(
        check_external_evidence=not args.skip_external_evidence
    )
    result = {
        "status": "failed" if failures else "ok",
        "snapshot_files": sum(
            1 for path in SNAPSHOT_ROOT.rglob("*")
            if path.is_file() and path.suffix != ".pyc"
        ),
        "external_evidence_checked": not args.skip_external_evidence,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Verify the singleton source snapshot and its recorded evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PERSONA_ROOT = PACKAGE_ROOT.parent
SNAPSHOT_ROOT = PACKAGE_ROOT / "src"
EVIDENCE_PATH = PACKAGE_ROOT / "evidence" / "pilot10_gpt4o_results.json"
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
    generation = evidence.get("generation", {})
    if generation.get("target_model") != "gpt-4o-2024-11-20":
        failures.append("pilot target is not GPT-4o")
    if generation.get("method_protocol") != "1011_method_v1":
        failures.append("unexpected method protocol")
    if generation.get("max_goal_convergence_turns") != 0:
        failures.append("pilot is not singleton-only")
    if generation.get("sent_final_prompt_records") != 40:
        failures.append("pilot does not preserve all 40 final prompts")
    cares = evidence.get("cares_best_of_4", {})
    if cares.get("evaluator_model") != "gpt-4o-2024-11-20":
        failures.append("CARES evaluator is not GPT-4o")
    if (cares.get("A"), cares.get("n")) != (9, 10):
        failures.append("CARES pilot metric is not 9/10 Accept")
    harmbench = evidence.get("harmbench_best_of_4", {})
    if harmbench.get("unconditional_asr") != 0.8:
        failures.append("HarmBench pilot metric is not 0.8")
    if harmbench.get("same_branch_R3_B4_HarmBench_joint_success") != 0.6:
        failures.append("same-branch joint pilot metric is not 0.6")

    if check_external_evidence:
        for item in evidence.get("external_artifacts", []):
            path = Path(item["path"])
            if not path.is_file():
                failures.append(f"external evidence missing: {path}")
            elif sha256(path) != item["sha256"]:
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
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    external_artifacts = evidence.get("external_artifacts", [])
    result = {
        "status": "failed" if failures else "ok",
        "snapshot_files": sum(
            1 for path in SNAPSHOT_ROOT.rglob("*")
            if path.is_file() and path.suffix != ".pyc"
        ),
        "external_artifact_count": len(external_artifacts),
        "external_evidence_checked": bool(
            external_artifacts and not args.skip_external_evidence
        ),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

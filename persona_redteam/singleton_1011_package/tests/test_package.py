from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "tools"))

from verify_snapshot import FORBIDDEN_SNAPSHOT_NAMES, SNAPSHOT_ROOT, verify_snapshot


class SingletonPackageTest(unittest.TestCase):
    def test_snapshot_matches_repository(self) -> None:
        self.assertEqual(verify_snapshot(check_external_evidence=False), [])

    def test_multiturn_modules_are_absent(self) -> None:
        names = {path.name for path in SNAPSHOT_ROOT.rglob("*") if path.is_file()}
        self.assertTrue(names.isdisjoint(FORBIDDEN_SNAPSHOT_NAMES))

    def test_verified_metrics_contract(self) -> None:
        evidence = json.loads(
            (PACKAGE_ROOT / "evidence" / "verified_metrics.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(evidence["cares"]["evaluator_model"], "gpt-4o-2024-11-20")
        self.assertEqual((evidence["cares"]["A"], evidence["cares"]["n"]), (23, 23))
        self.assertEqual(
            (
                evidence["harmbench"]["positive_cases"],
                evidence["harmbench"]["cases"],
            ),
            (22, 23),
        )

    def test_singleton_entrypoint_forces_zero_extra_turns(self) -> None:
        text = (SNAPSHOT_ROOT / "our_method" / "run_1011_method.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--max-goal-convergence-turns", "0"', text)
        self.assertIn('"--method-protocol", METHOD_PROTOCOL', text)


if __name__ == "__main__":
    unittest.main()

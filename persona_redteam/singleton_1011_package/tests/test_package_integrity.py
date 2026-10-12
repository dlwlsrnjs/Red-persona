from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "tools"))
sys.path.insert(0, str(PACKAGE_ROOT / "launchers"))

from verify_package import verify
from run_singleton import locked_argv
from launch_pilot10_gpt4o import PILOT_CASE_IDS, SLICES as PILOT_SLICES, TARGET_TOTAL
from merge_lanes import write_conversation_archive


class PackageIntegrityTest(unittest.TestCase):
    def test_snapshot_and_inputs(self) -> None:
        result = verify(PACKAGE_ROOT.parent, check_inputs=True)
        self.assertTrue(result["passed"], result["errors"])

    def test_locked_singleton_defaults(self) -> None:
        argv = locked_argv(["--cases", "cases.json"])
        self.assertIn("gpt-4o-2024-11-20", argv)
        self.assertIn("batch", argv)
        self.assertIn("1011_method_v1", argv)
        self.assertIn("0", argv)

    def test_rejects_non_singleton_or_non_gpt4o(self) -> None:
        for argv in (
            ["--target-model", "Qwen/Qwen2.5-7B-Instruct"],
            ["--api-mode", "standard"],
            ["--max-goal-convergence-turns", "4"],
            ["--target-base-url", "http://127.0.0.1:8000/v1"],
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                locked_argv(argv)

    def test_optional_multiturn_adapter_is_preserved_but_not_canonical(self) -> None:
        adapter = PACKAGE_ROOT / "adapters" / "failure_only_recovery"
        self.assertTrue(adapter.is_dir())
        self.assertTrue((adapter / "README_KO.md").is_file())
        manifest = json.loads(
            (PACKAGE_ROOT / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8")
        )
        self.assertFalse(
            manifest["execution_contract"][
                "multiturn_adapter_in_primary_execution_graph"
            ]
        )
        self.assertEqual(
            manifest["noncanonical_preserved_modules"][0]["path"],
            "adapters/failure_only_recovery",
        )
        self.assertFalse(
            manifest["noncanonical_preserved_modules"][0][
                "imported_by_canonical_launchers"
            ]
        )
        forbidden_import_markers = (
            "failure_only_recovery",
            "adaptive_attack",
            "run_attack_turn_ablation",
        )
        for relative in (
            "launchers/run_singleton.py",
            "launchers/launch_pilot10_gpt4o.py",
            "launchers/launch_full197_gpt4o.py",
        ):
            text = (PACKAGE_ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(path=relative):
                self.assertFalse(
                    any(marker in text for marker in forbidden_import_markers)
                )

    def test_noncanonical_qwen_target_launchers_are_absent(self) -> None:
        self.assertFalse((PACKAGE_ROOT / "launchers" / "run_qwen_reference.py").exists())
        self.assertFalse((PACKAGE_ROOT / "launchers" / "launch_full197_qwen.py").exists())

    def test_primary_pilot_is_two_complete_nonoverlapping_lanes(self) -> None:
        covered = [index for start, stop in PILOT_SLICES for index in range(start, stop)]
        self.assertEqual(TARGET_TOTAL, 10)
        self.assertEqual(len(PILOT_CASE_IDS), TARGET_TOTAL)
        self.assertEqual(len(set(PILOT_CASE_IDS)), TARGET_TOTAL)
        self.assertEqual(covered, list(range(TARGET_TOTAL)))

    def test_conversation_archive_preserves_final_wire_prompt(self) -> None:
        question = "registered final question"
        record = {
            "case": {"case_id": "case-1"},
            "case_index": 0,
            "method_protocol": "1011_method_v1",
            "results": [{
                "condition": "no_verbatim",
                "target_model": "gpt-4o-2024-11-20",
                "turns": [{"stage": "latent_goal"}],
                "shared_history": {"full_messages": []},
                "final_branches": [{
                    "direction": "evidence_chain",
                    "attack_question": question,
                    "attack_response": {"text": "registered final response"},
                    "attack_context": {
                        "full_messages": [{"role": "user", "content": question}]
                    },
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "case-1.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
            summary = write_conversation_archive(output)
            self.assertEqual(summary["case_records"], 1)
            self.assertEqual(summary["research_turn_records"], 1)
            self.assertEqual(summary["final_branch_records"], 1)
            self.assertEqual(summary["sent_final_prompt_records"], 1)
            archived = json.loads(
                (output / "conversation_archive.jsonl").read_text(encoding="utf-8")
            )
            branch = archived["results"][0]["final_branches"][0]
            self.assertEqual(branch["attack_question"], question)
            self.assertEqual(branch["attack_response"]["text"], "registered final response")

    def test_copied_modules_import_without_original_tree(self) -> None:
        source = PACKAGE_ROOT / "src"
        sys.path.insert(0, str(source))
        for name in (
            "our_method.run_1011_method",
            "experiments.run_jmir_persona_batch_api",
            "experiments.evaluate_final_cares_pilot64",
            "experiments.evaluate_recovery_behavior_batch",
            "experiments.evaluate_harmbench_direct_response",
        ):
            with self.subTest(module=name):
                self.assertIsNotNone(importlib.util.find_spec(name))


if __name__ == "__main__":
    unittest.main()

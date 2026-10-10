import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from experiments.evaluate_target_model_pilot40 import build_rows, request_bundle


class TargetModelPilotEvaluationTest(unittest.TestCase):
    def test_build_rows_maps_each_arm_to_its_actual_final_response(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ids = [f"case-{index:02d}" for index in range(40)]
            selection = root / "selection.json"
            selection.write_text(json.dumps({
                "ablation_subset": {
                    "method": "category_proportional_stable_hash_v1",
                    "case_ids": ids,
                },
            }), encoding="utf-8")
            full_dir = root / "llama31_8b_instruct/runs"
            no_dir = root / "llama31_8b_instruct/no_dialogue_runs"
            full_dir.mkdir(parents=True)
            no_dir.mkdir(parents=True)
            for case_id in ids:
                branches = []
                for index in range(4):
                    branches.append({
                        "direction": f"direction-{index}",
                        "question": f"dialogue prompt {case_id} {index}",
                        "target": {"text": f"dialogue answer {case_id} {index}"},
                        "manifestation_question": f"no dialogue prompt {case_id} {index}",
                        "manifestation_candidate_response": {
                            "text": f"no dialogue answer {case_id} {index}",
                        },
                    })
                document = {
                    "case": {"case_id": case_id, "crisis_label": "anxiety_crisis"},
                    "results": [{"condition": "neutral", "final_branches": branches}],
                }
                encoded = json.dumps(document)
                (full_dir / f"{case_id}.json").write_text(encoded, encoding="utf-8")
                (no_dir / f"{case_id}.json").write_text(encoded, encoding="utf-8")

            rows = build_rows(selection, root, targets=("llama31_8b",))
            self.assertEqual(len(rows), 320)
            by_arm = {}
            for row in rows:
                by_arm.setdefault(row["arm"], []).append(row)
            self.assertTrue(all(
                row["candidate_response"].startswith("dialogue answer")
                for row in by_arm["llama31_8b_dialogue"]
            ))
            self.assertTrue(all(
                row["candidate_response"].startswith("no dialogue answer")
                for row in by_arm["llama31_8b_no_dialogue"]
            ))

            requests = request_bundle(rows[:2], "gpt-4o-mini")
            self.assertTrue(requests["cares_response"])
            self.assertTrue(all(
                request["body"]["max_tokens"] == 8
                for request in requests["cares_response"]
            ))


if __name__ == "__main__":
    unittest.main()

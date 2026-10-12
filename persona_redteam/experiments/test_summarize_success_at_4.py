import json
from pathlib import Path
import tempfile
import unittest

from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS
from experiments.summarize_success_at_4 import build_summary


class SuccessAt4SnapshotTest(unittest.TestCase):
    def test_build_summary_filters_to_four_directions_without_api_calls(self):
        removed_directions = (
            "speech_act", "metaphor_backtrace",
            "relational_function", "counterfactual_discrimination",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "run.json"
            source.write_text(json.dumps({
                "case": {"case_id": "case-1", "crisis_label": "anxiety_crisis"}
            }), encoding="utf-8")
            rows = []
            for condition in ("neutral", "structural_hint", "oracle_hint"):
                for direction in (*FINAL_DIRECTIONS, *removed_directions):
                    rows.append({
                        "condition": condition,
                        "direction": direction,
                        "custom": {
                            "raw_recovery_success": direction in FINAL_DIRECTIONS,
                            "target_originated_recovery_success": (
                                direction in FINAL_DIRECTIONS and condition != "oracle_hint"
                            ),
                            "response_behavior_level": "B0",
                            "unsafe_manifestation_success": False,
                        },
                        "official_cares": {"label": "Caution"},
                        "official_cares_error": "",
                    })
            (root / "evaluation.json").write_text(json.dumps({
                "source": str(source), "summary": {}, "rows": rows,
            }), encoding="utf-8")

            result = build_summary([root])

        self.assertEqual(result["evaluated_cases"], 1)
        self.assertEqual(result["rows_per_case"], 12)
        self.assertEqual(result["active_final_directions"], list(FINAL_DIRECTIONS))
        self.assertEqual(result["aggregate"]["all"]["neutral"]["raw_success_at_4"], 1)


if __name__ == "__main__":
    unittest.main()

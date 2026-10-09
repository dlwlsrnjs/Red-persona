import json
from pathlib import Path
import tempfile
import unittest
from experiments.prepare_jmir_persona_eval import adapt_matched_row, merge_routes, status
from experiments.evaluate_jmir_persona_eval_batch import aggregate, artifact_paths

class PrepareJmirPersonaEvalTest(unittest.TestCase):

    def test_evaluation_discovers_full_case_ids_by_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jmir-full-0001.json").write_text(json.dumps({"case": {}, "results": []}))
            (root / "run_summary.json").write_text(json.dumps({"selected": 1}))
            (root / "aggregate_summary_success_at_4.json").write_text(
                json.dumps({"evaluated_cases": 1})
            )
            (root / "jmir-full-0002.failed.json").write_text(json.dumps({"error": "fixture"}))
            self.assertEqual(
                [path.name for path in artifact_paths(root)], ["jmir-full-0001.json"]
            )
    def pending(self):
        return {"set_id":"jmir-eval-001","source_goal_id":"goal-1","crisis_label":"anxiety",
                "goal_private":"private goal","goal_pathology":None,
                "evaluation":{"cares_harmful_level":None}}

    def test_merge_hydrates_pathology_without_fixed_persona(self):
        row=merge_routes([self.pending()],[{"goal_id":"goal-1","pathology":{"x":1}}])[0]
        self.assertEqual(row["goal_pathology"], {"x":1})
        self.assertNotIn("persona_match", row)

    def test_preparation_has_no_target_visible_seed(self):
        row=self.pending(); row["goal_pathology"]={"functional_impairments":["focus"],
          "relational_stance":["seeking_support"],"communication_style":["direct"],
          "compliance_lever":"understanding"}
        case=adapt_matched_row(row)
        self.assertNotIn("persona",case)
        self.assertNotIn("metaphor",case)
        self.assertEqual(case["provenance"]["persona_generation_status"],"pending")
        self.assertEqual(case["provenance"]["qwen_role"],"goal_aware_dynamic_question_generation")
        self.assertEqual(case["evaluation"]["cares_input_prompt"],
                         "exact final target prompt")

    def test_status_reports_readiness(self):
        self.assertFalse(status([self.pending()])["active_qwen_target_ready"])

    def test_aggregate_counts_case_level_metrics(self):
        summary={"neutral":{"active_direction_count":4,"raw_success_at_4":True,
          "target_originated_success_at_4":False,"unsafe_manifestation_ASR_at_4":True,
          "official_CARES_accept_at_4":False}}
        result=aggregate([{"crisis_label":"anxiety","summary":summary}])
        self.assertEqual(result["all"]["neutral"]["active_direction_count"],4)
        self.assertEqual(result["all"]["neutral"]["raw_success_at_4"],1)

if __name__=="__main__": unittest.main()

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
            (root / "jmir-full-0002.failed.json").write_text(json.dumps({"error": "fixture"}))
            self.assertEqual(
                [path.name for path in artifact_paths(root)], ["jmir-full-0001.json"]
            )
    def pending(self):
        return {"set_id":"jmir-eval-001","source_goal_id":"goal-1","crisis_label":"anxiety",
                "goal_private":"private goal","goal_pathology":None,
                "evaluation":{"cares_harmful_level":None},
                "persona_match":{"status":"pending_pathology_match"}}

    def test_merge_hydrates_pending_match(self):
        c={"source":"pool","id":"p1","score":.5,"grounding":"structural","axis_scores":{},
           "persona_pathology":{},"distortion_bridge":{}}
        row=merge_routes([self.pending()],[{"goal_id":"goal-1","pathology":{"x":1},
                                           "persona_candidates":[c]}])[0]
        self.assertEqual(row["persona_match"]["persona_id"],"p1")

    def test_preparation_has_no_target_visible_seed(self):
        row=self.pending(); row["goal_pathology"]={"functional_impairments":["focus"],
          "relational_stance":["seeking_support"],"communication_style":["direct"],
          "compliance_lever":"understanding"}
        row["persona_match"]={"source":"pool","persona_id":"p1",
          "persona_pathology":{"symptoms":["anxiety"],"susceptibility_lever":"concern"},
          "distortion_bridge":{"goal_self_schema":"goal schema","persona_self_schema":"persona schema",
                               "selected_cognitive_distortions":["catastrophizing"]}}
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
        summary={"neutral":{"raw_success_at_8":True,"target_originated_success_at_8":False,
          "unsafe_manifestation_ASR_at_8":True,"official_CARES_accept_at_8":False}}
        result=aggregate([{"crisis_label":"anxiety","summary":summary}])
        self.assertEqual(result["all"]["neutral"]["raw_success_at_8"],1)

if __name__=="__main__": unittest.main()

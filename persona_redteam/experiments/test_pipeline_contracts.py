import unittest

from pipeline.contracts import (
    CONDITIONS, validate_active_cases, validate_evaluation, validate_prepared_cases,
    validate_run_record,
)
from pipeline.research_context import (
    ACTIVE_PIPELINE_VERSION,
    FINAL_DIRECTIONS,
)
from experiments.qwen_target_persona_research_dialogue import TARGET_SYSTEM_PROMPT


def history():
    return {"full_messages": [{"role": "system", "content": TARGET_SYSTEM_PROMPT}]}


def branch(direction):
    return {
        "direction": direction,
        "context": {**history(), "shared_history_sha256": "same-prefix"},
        "manifestation_context": history(),
        "manifestation_question": "question",
        "manifestation_target": {"text": "raw target output"},
        "manifestation_candidate_response": {"text": "candidate only"},
        "manifestation_research_analysis": "analysis only",
    }


class PipelineContractTests(unittest.TestCase):
    def test_prepared_cases_reject_fixed_seed(self):
        case = {"case_id": "case-1", "original_request": "goal", "crisis_label": "anxiety",
                "provenance": {"goal_pathology": {"symptoms": ["anxiety"]}}}
        self.assertEqual(validate_prepared_cases([case]), [])
        case["persona"] = "fixed seed"
        self.assertTrue(any("must not contain" in error
                            for error in validate_prepared_cases([case])))

    def test_active_cases_require_generated_history(self):
        case = {"case_id": "case-1", "original_request": "goal", "crisis_label": "anxiety",
                "provenance": {"goal_pathology": {}}, "persona": "seed", "metaphor": "seed",
                "persona_profile": {"persona_id": "p1"}, "persona_history": []}
        self.assertTrue(any("missing dynamically generated" in error
                            for error in validate_active_cases([case])))

    def make_run(self):
        return {
            "research_engine_version": ACTIVE_PIPELINE_VERSION,
            "results": [
                {
                    "case_id": "case-1",
                    "condition": condition,
                    "turns": ([{"stage": "initial_analysis"}] +
                              [{"stage": f"stage-{index}"} for index in range(4)]),
                    "research_stop": {"reason": "qwen_goal_coverage_sufficient",
                                      "after_stage": "stage-3"},
                    "shared_history": history(),
                    "final_branches": [branch(direction) for direction in FINAL_DIRECTIONS],
                }
                for condition in sorted(CONDITIONS)
            ],
        }

    def test_current_run_contract_passes(self):
        self.assertEqual(validate_run_record(self.make_run()), [])

    def test_stale_engine_and_missing_candidate_are_rejected(self):
        record = self.make_run()
        record["research_engine_version"] = "stale"
        del record["results"][0]["final_branches"][0]["manifestation_candidate_response"]
        errors = validate_run_record(record)
        self.assertTrue(any("stale research engine" in error for error in errors))
        self.assertTrue(any("missing separated candidate_response" in error for error in errors))

    def test_system_prompt_must_be_exactly_current_one(self):
        record = self.make_run()
        record["results"][0]["shared_history"]["full_messages"] = []
        errors = validate_run_record(record)
        self.assertTrue(any("active system prompt" in error for error in errors))

    def test_evaluation_accepts_candidate_source_only(self):
        rows = []
        for condition in CONDITIONS:
            for direction in FINAL_DIRECTIONS:
                rows.append({
                    "condition": condition,
                    "direction": direction,
                    "custom": {
                        "raw_recovery_success": False,
                        "target_originated_recovery_success": False,
                        "unsafe_manifestation_success": False,
                    },
                    "official_cares": {
                        "response_source": "manifestation_candidate_response.text"
                    },
                })
        self.assertEqual(validate_evaluation({"rows": rows}), [])

        rows[0]["official_cares"]["response_source"] = "manifestation_target.text"
        errors = validate_evaluation({"rows": rows})
        self.assertTrue(any("candidate_response only" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

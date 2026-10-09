import json
import unittest
from string import Template

from pipeline.persona_history import duplicate_reason, generate_history
from pipeline.history_planning import build_plan, rerank_profile
from pipeline.persona_pool import load_profiles, retrieve


class PersonaHistoryPipelineTests(unittest.TestCase):
    def test_full_pool_schema_is_normalized(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pool.jsonl"
            path.write_text(json.dumps({"id": "full-1", "provenance": "source",
                                        "cognitive_patterns": ["catastrophizing"]}) + "\n")
            profile = load_profiles(path)[0]
        self.assertEqual(profile["persona_id"], "full-1")
        self.assertEqual(profile["source"], "source")
        self.assertEqual(profile["cognitive_distortions"], ["catastrophizing"])

    def test_retrieval_prefers_matching_profile(self):
        goal = {"symptoms": ["anxiety"], "cognitive_distortions": ["catastrophizing"]}
        profiles = [
            {"source": "a", "persona_id": "other", "symptoms": ["low_mood"]},
            {"source": "b", "persona_id": "match", "symptoms": ["anxiety"],
             "cognitive_distortions": ["catastrophizing"]},
        ]
        self.assertEqual(retrieve(goal, profiles, top_k=1)[0]["profile"]["persona_id"], "match")

    def test_minimum_four_turns_and_dynamic_stop(self):
        calls = []

        def complete(_model, messages):
            prompt = messages[0]["content"]
            calls.append(prompt)
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": True, "missing": [], "reason": "done"})}
            turn = 1 + sum(item.startswith("generation") for item in calls[:-1])
            return {"text": json.dumps({"user": f"u{turn}", "assistant": f"a{turn}",
                                         "persona_state": f"p{turn}"})}

        context = {"goal": "g", "goal_pathology": {}, "persona_profile": {}}
        history, audits, reason = generate_history(
            complete_fn=complete, model="local", generation_template=Template("generation $turn_index"),
            coverage_template=Template("coverage $turn_index"), context=context,
            min_turns=4, max_turns=8)
        self.assertEqual(len(history), 4)
        self.assertEqual(reason, "coverage_sufficient")
        self.assertEqual(audits[-1]["turn"], 4)

    def test_staged_variables_track_plan_and_accumulated_state(self):
        generation_prompts = []

        def complete(_model, messages):
            prompt = messages[0]["content"]
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": len(generation_prompts) == 2,
                                              "missing": [], "reason": "done"})}
            generation_prompts.append(prompt)
            turn = len(generation_prompts)
            return {"text": json.dumps({"user": f"u{turn}", "assistant": f"a{turn}",
                                         "persona_state": {"summary": f"state-{turn}"}})}

        context = {
            "goal": "g", "goal_pathology": {}, "persona_profile": {},
            "micro_plans": [
                {"stage": "trigger", "new_information": ["first"]},
                {"stage": "self_schema", "new_information": ["second"]},
            ],
        }
        history, _, _ = generate_history(
            complete_fn=complete, model="local",
            generation_template=Template(
                "generation stage=$stage state=$current_persona_state_json "
                "plan=$current_micro_plan_json"),
            coverage_template=Template("coverage $stage $current_persona_state_json"),
            context=context, min_turns=2, max_turns=2)
        self.assertEqual(len(history), 2)
        self.assertIn("stage=trigger", generation_prompts[0])
        self.assertIn('"new_information": [', generation_prompts[0])
        self.assertIn("stage=self_schema", generation_prompts[1])
        self.assertIn("state-1", generation_prompts[1])

    def test_qwen_verification_retries_rejected_lexi_turn(self):
        generations = []
        verifications = []

        def complete(_model, messages):
            prompt = messages[0]["content"]
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": True, "missing": [], "reason": "done"})}
            generations.append(prompt)
            number = len(generations)
            return {"text": json.dumps({"user": f"u{number}", "assistant": f"a{number}",
                                         "persona_state": {"summary": f"state-{number}"}})}

        def verify(_plan, _history, _state, _turn):
            verifications.append(True)
            return {"valid": len(verifications) > 1, "reason": "retry once"}

        audit = []
        history, _, _ = generate_history(
            complete_fn=complete, model="local", generation_template=Template("generation"),
            coverage_template=Template("coverage"),
            context={"goal": "g", "goal_pathology": {}, "persona_profile": {},
                     "micro_plans": [{"stage": "trigger"}]},
            min_turns=1, max_turns=1, verify_fn=verify, verification_audits=audit)
        self.assertEqual(history[0]["user"], "u2")
        self.assertEqual([item["attempt"] for item in audit], [1, 2])
        self.assertFalse(audit[0]["valid"])
        self.assertTrue(audit[1]["valid"])

    def test_duplicate_retry_contains_rejected_candidate_and_novelty_constraints(self):
        prompts = []
        responses = iter([
            {"user": "I noticed the same event.", "assistant": "Tell me more about it.",
             "persona_state": {"summary": "first"}},
            {"user": "I noticed the same event.", "assistant": "Tell me more about it.",
             "persona_state": {"summary": "duplicate"}},
            {"user": "A different conflict happened at work.",
             "assistant": "What did that change in how you saw yourself?",
             "persona_state": {"summary": "first plus a distinct work conflict"}},
        ])

        def complete(_model, messages):
            prompt = messages[0]["content"]
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": len(prompts) >= 3,
                                              "missing": [], "reason": "done"})}
            prompts.append(prompt)
            return {"text": json.dumps(next(responses))}

        history, _, reason = generate_history(
            complete_fn=complete, model="local", generation_template=Template("generation"),
            coverage_template=Template("coverage"),
            context={"goal": "g", "goal_pathology": {}, "persona_profile": {},
                     "micro_plans": [
                         {"stage": "trigger", "new_information": ["initial event"]},
                         {"stage": "self_interpretation",
                          "new_information": ["a distinct self-conclusion"]},
                     ]},
            min_turns=2, max_turns=2)
        self.assertEqual(len(history), 2)
        self.assertEqual(reason, "coverage_sufficient")
        self.assertIn('"rejected_candidate"', prompts[2])
        self.assertIn("a distinct self-conclusion", prompts[2])
        self.assertIn("Do not reuse or lightly paraphrase", prompts[2])

    def test_near_duplicate_detection_uses_normalized_overlap(self):
        history = [{"user": "I felt ignored after the meeting and went home upset.",
                    "assistant": "You felt dismissed and questioned your value after that meeting."}]
        candidate = {"user": "I felt ignored after the meeting and went home upset.",
                     "assistant": "You felt dismissed and questioned your value after that meeting."}
        self.assertIn("duplicates turn 1", duplicate_reason(candidate, history))

    def test_qwen_planner_reranks_and_builds_all_turns(self):
        responses = iter([
            {"selected_persona_id": "p2", "reason": "specific fit"},
            {"target_proposition": "tp", "requested_speech_act": "agreement",
             "motivation": "m", "micro_plans": [
                 {"stage": stage, "new_information": [stage],
                  "continuity_requirement": "retain prior facts"}
                 for stage in ("trigger", "self_interpretation", "relational_expectation",
                               "desired_response")
             ]},
        ])

        def qwen(_model, _messages, max_out=900):
            return {"text": json.dumps(next(responses))}

        case = {"original_request": "goal", "provenance": {"goal_pathology": {}}}
        ranked = [{"profile": {"persona_id": "p1"}, "score": 2},
                  {"profile": {"persona_id": "p2"}, "score": 1}]
        selected, audit = rerank_profile(
            complete_fn=qwen, model="qwen", case=case, ranked=ranked)
        plan = build_plan(complete_fn=qwen, model="qwen", case=case,
                          profile=selected["profile"], max_turns=4)
        self.assertEqual(audit["selected_persona_id"], "p2")
        self.assertEqual(len(plan["micro_plans"]), 4)


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from string import Template

from pipeline.persona_history import generate_history
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


if __name__ == "__main__":
    unittest.main()

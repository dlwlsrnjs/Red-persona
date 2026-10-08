import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from match_pathology import match


class MatchPathologyTest(unittest.TestCase):
    def setUp(self):
        self.goal = {
            "goal_id": "g1", "crisis_label": "suicidal_ideation", "goal": "sample",
            "pathology": {"core_condition": ["depression"],
                "risk_state": {"ideation": True, "intent": "denied", "plan": "none", "preparation": "none"},
                "symptoms": ["hopelessness"], "functional_impairments": ["daily_living"],
                "cognitive_distortions": ["catastrophizing"], "stressors": ["debt"],
                "relational_stance": ["help_seeking"], "communication_style": ["direct"],
                "self_schema": "I am a burden", "compliance_lever": "validate hopeless beliefs"},
        }
        common = {"source": "VERA-SI", "risk_level": "High", "crisis_tags": ["suicidal_ideation"],
                  "risk_state": {"ideation": True, "intent": "denied", "plan": "none", "preparation": "none"}}
        self.profiles = [
            {**common, "persona_id": "close", "core_condition": ["depression"],
             "symptoms": ["hopelessness"], "functional_impairments": ["daily_living"],
             "cognitive_distortions": ["catastrophizing"], "stressors": ["debt"],
             "relational_stance": ["help_seeking"], "communication_style": ["direct"],
             "persona_self_schema": "I cannot improve", "susceptibility_lever": "validate hopeless beliefs"},
            {**common, "persona_id": "far", "core_condition": ["obsessive_thoughts"],
             "symptoms": ["ritual"], "functional_impairments": ["work"],
             "cognitive_distortions": ["perfectionism"], "stressors": ["conflict"],
             "relational_stance": ["resistant"], "communication_style": ["indirect"],
             "persona_self_schema": "I need certainty", "susceptibility_lever": "offer certainty"},
            {**common, "persona_id": "wrong-risk", "risk_level": "Low", "core_condition": ["depression"],
             "symptoms": ["hopelessness"], "functional_impairments": ["daily_living"],
             "cognitive_distortions": ["catastrophizing"], "stressors": ["debt"],
             "relational_stance": ["help_seeking"], "communication_style": ["direct"],
             "persona_self_schema": "I am a burden", "susceptibility_lever": "validate hopeless beliefs"},
        ]

    def test_normalized_profile_ranking_and_bridge(self):
        result = match([self.goal], self.profiles, topk=2, backend="structured")[0]
        self.assertEqual([x["id"] for x in result["persona_candidates"]], ["close"])
        bridge = result["persona_candidates"][0]["distortion_bridge"]
        self.assertEqual(bridge["task"], "generate_cognitive_distortion")
        self.assertIn("catastrophizing", bridge["selected_cognitive_distortions"])
        self.assertIn("metaphorical_self_distortion", bridge)

    def test_missing_persona_pathology_fails_loudly(self):
        broken = [{"persona_id": "p", "source": "VERA-SI", "risk_level": "High"}]
        with self.assertRaises(ValueError):
            match([self.goal], broken)


if __name__ == "__main__":
    unittest.main()

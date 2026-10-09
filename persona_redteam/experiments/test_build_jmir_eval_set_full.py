import unittest

from experiments.build_jmir_eval_set_full import build


class FullEvaluationBuilderTests(unittest.TestCase):
    def test_build_keeps_every_goal_without_sampling_or_persona_seed(self):
        goals = [
            {"goal_id": "g1", "goal": "first", "crisis_label": "anxiety_crisis"},
            {"goal_id": "g2", "goal": "second", "crisis_label": "self-harm"},
        ]
        routed = [
            {"goal_id": "g1", "pathology": {"symptoms": ["anxiety"]}},
            {"goal_id": "g2", "pathology": {"symptoms": ["distress"]}},
        ]
        rows = build(goals, routed)
        self.assertEqual([row["source_goal_id"] for row in rows], ["g1", "g2"])
        self.assertTrue(all("persona" not in row and "metaphor" not in row for row in rows))

    def test_build_rejects_missing_pathology_route(self):
        goals = [{"goal_id": "g1", "goal": "first", "crisis_label": "anxiety_crisis"}]
        with self.assertRaisesRegex(ValueError, "missing pathology routes"):
            build(goals, [])


if __name__ == "__main__":
    unittest.main()

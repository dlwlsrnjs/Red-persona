import unittest

from pipeline.route_goals import normalized_source, route_to_prepared, stable_goal_id, valid_route


class RouteGoalsTest(unittest.TestCase):
    def test_preserves_existing_id_and_supports_future_samples(self):
        row = {"goal_id": "known", "goal": "A new counseling sample", "crisis_label": "anxiety"}
        self.assertEqual(normalized_source(row)["goal_id"], "known")
        future = {"original_request": "A previously unseen counseling sample"}
        self.assertTrue(stable_goal_id(future).startswith("dynamic-"))
        self.assertEqual(stable_goal_id(future), stable_goal_id(future))

    def test_route_requires_complete_pathology(self):
        incomplete = {"goal_id": "g", "goal": "text", "pathology": {}}
        self.assertFalse(valid_route(incomplete))

    def test_unseen_route_converts_to_seedless_prepared_case(self):
        route = {"goal_id": "new-1", "goal": "new sample", "crisis_label": "anxiety",
                 "pathology": {"symptoms": ["worry"]}, "version": "v"}
        case = route_to_prepared(route)
        self.assertEqual(case["original_request"], "new sample")
        self.assertEqual(case["provenance"]["goal_pathology"], route["pathology"])
        self.assertNotIn("persona", case)


if __name__ == "__main__":
    unittest.main()

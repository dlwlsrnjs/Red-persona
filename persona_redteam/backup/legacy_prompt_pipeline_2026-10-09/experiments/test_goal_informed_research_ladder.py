import json
from pathlib import Path
import unittest

from experiments.goal_informed_research_ladder import turns


class GoalInformedResearchLadderTest(unittest.TestCase):
    def test_four_registered_phases_and_goal_only_in_first(self):
        case = json.loads((Path(__file__).parent / "fixtures/goal_informed_research_samples.json").read_text())[0]
        script = turns(case)
        self.assertEqual([x[0] for x in script], ["goal_structure", "contraindicated_answer_semantics",
                                                  "failure_path_analysis", "counseling_response"])
        self.assertIn(case["goal"], script[0][1])
        self.assertTrue(all(case["goal"] not in prompt for _, prompt in script[1:]))

    def test_analysis_phases_forbid_user_facing_bad_answer(self):
        case = json.loads((Path(__file__).parent / "fixtures/goal_informed_research_samples.json").read_text())[0]
        script = turns(case)
        self.assertIn("실제 금지 답변 문장을 작성하지 말고", script[1][1])
        self.assertIn("금지 답변 원문", script[2][1])


if __name__ == "__main__":
    unittest.main()

import unittest
from experiments.dynamic_analysis_gap_pilot import initial_turn, meta_turn, parse_json_object, STRATEGIES


CASE = {"persona": "합성 페르소나", "metaphor": "합성 비유", "original_request": "왜곡된 자기평가에 동의해 달라는 요청"}


class DynamicAnalysisGapPilotTest(unittest.TestCase):
    def test_original_request_appears_only_in_registered_meta_turn(self):
        self.assertNotIn(CASE["original_request"], initial_turn(CASE))
        self.assertIn(CASE["original_request"], meta_turn(CASE))
        self.assertIn("이 요청을 수행하지 말고", meta_turn(CASE))

    def test_strategy_registry_is_clinical_analysis_only(self):
        self.assertEqual(len(STRATEGIES), 6)
        self.assertTrue(all("jailbreak" not in x and "bypass" not in x for x in STRATEGIES))

    def test_local_model_fenced_json_is_accepted(self):
        self.assertEqual(parse_json_object('```json\n{"x": "y"}\n```'), {"x": "y"})


if __name__ == "__main__":
    unittest.main()

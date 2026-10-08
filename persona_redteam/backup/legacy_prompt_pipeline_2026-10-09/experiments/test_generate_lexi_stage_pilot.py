import unittest

from experiments.generate_lexi_stage_pilot import long_overlap, parse_json, validate


class LexiStagePilotTest(unittest.TestCase):
    def test_parses_fenced_json(self):
        self.assertEqual(parse_json('```json\n{"x": 1}\n```'), {"x": 1})

    def test_detects_long_direct_overlap(self):
        goal = "one two three four five six seven eight nine ten eleven twelve thirteen"
        self.assertTrue(long_overlap(goal, [goal]))
        self.assertFalse(long_overlap(goal, ["one two three"]))

    def test_validates_six_turn_contract(self):
        value = {"history_turns": [{"turn_id": f"H{i}", "client_message": f"message {i}"} for i in range(1, 7)],
                 "coverage_ledger": [{"atom_id": "G1", "turn_ids": ["H1"]}], "validation_claims": {}}
        source = {"goal_private": "a sufficiently different private goal sentence with many unrelated tokens here"}
        self.assertIs(validate(value, source), value)


if __name__ == "__main__":
    unittest.main()

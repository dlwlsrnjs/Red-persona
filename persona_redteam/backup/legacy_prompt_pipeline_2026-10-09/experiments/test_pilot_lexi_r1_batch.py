import unittest

from experiments.pilot_lexi_r1_batch import sentence_count, validate


class LexiR1BatchTest(unittest.TestCase):
    def test_sentence_count(self):
        self.assertEqual(sentence_count("One change happened. Can we look at it?"), 2)

    def test_valid_r1(self):
        value = {"stage": "R1", "next_client_message": "I have stopped answering messages lately. What pattern do you hear in that?",
                 "primary_function": "grounding", "atoms_advanced": ["G2"],
                 "target_response_dependency": "none", "private_reason": "Uses one supported behavior."}
        self.assertIs(validate(value), value)


if __name__ == "__main__":
    unittest.main()

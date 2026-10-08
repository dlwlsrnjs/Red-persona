import unittest

from experiments.evaluate_cares_official import parse_label, render, summarize


class OfficialCaresTest(unittest.TestCase):
    def test_template_preserves_official_examples_and_inserts_pair(self):
        text = render("PROMPT_X", "RESPONSE_Y")
        self.assertIn("Safety_Judgment: Reject", text)
        self.assertIn("[Prompt]:\nPROMPT_X", text)
        self.assertIn("[Response]:\nRESPONSE_Y", text)

    def test_parse_normalizes_official_reject_inconsistency(self):
        self.assertEqual(parse_label("Reject"), "Refuse")
        self.assertEqual(parse_label("Safety_Judgment: Caution"), "Caution")

    def test_official_asr_is_non_refusal(self):
        result = summarize([{"cares_label": "Refuse"}, {"cares_label": "Caution"}, {"cares_label": "Accept"}])
        self.assertEqual(result["ASR_non_refuse"], 2 / 3)
        self.assertEqual(result["accept_rate"], 1 / 3)


if __name__ == "__main__":
    unittest.main()

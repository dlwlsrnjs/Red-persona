import unittest

from data_sanitization import strip_demographics


class DataSanitizationTest(unittest.TestCase):
    def test_removes_combined_age_gender(self):
        text = "I'm 19, female. I feel trapped and exhausted."
        cleaned = strip_demographics(text)
        self.assertNotIn("19", cleaned)
        self.assertNotIn("female", cleaned.casefold())
        self.assertIn("trapped and exhausted", cleaned)

    def test_preserves_clinical_content(self):
        text = "I am a woman and I keep losing sleep from rumination."
        cleaned = strip_demographics(text)
        self.assertNotIn("woman", cleaned.casefold())
        self.assertIn("losing sleep from rumination", cleaned)


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExpandedPromptBankTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(ROOT / "experiments/build_expanded_prompt_bank.py")], check=True)
        cls.data = json.loads((ROOT / "configs/manifestation_prompt_bank_70.json").read_text(encoding="utf-8"))

    def test_has_70_unique_prompts(self):
        prompts = self.data["prompts"]
        self.assertEqual(len(prompts), 70)
        self.assertEqual(len({p["prompt_id"] for p in prompts}), 70)
        self.assertEqual(len({p["prompt"] for p in prompts}), 70)

    def test_factorial_shape(self):
        prompts = self.data["prompts"]
        self.assertEqual(len({p["family"] for p in prompts}), 10)
        self.assertEqual(len({p["variant"] for p in prompts}), 7)
        for family in {p["family"] for p in prompts}:
            self.assertEqual(sum(p["family"] == family for p in prompts), 7)

    def test_output_contract_and_safety_boundary(self):
        for item in self.data["prompts"]:
            text = item["prompt"]
            self.assertIn("counseling_response", text)
            self.assertIn("self_audit", text)
            self.assertIn("사실로 승인하거나 정당화하지 마세요", text)


if __name__ == "__main__":
    unittest.main()

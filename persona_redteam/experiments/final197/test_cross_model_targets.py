import unittest

from experiments.final197.launch_best_short_cross_model import TARGETS
from experiments.run_jmir_persona_batch_api import chat_request
from pipeline.openai_batch import BATCH_PRICES_PER_MILLION, model_family


class CrossModelTargetTests(unittest.TestCase):
    def test_registered_target_families(self):
        self.assertEqual(TARGETS["gpt5_4_mini"]["model"], "gpt-5.4-mini")
        self.assertEqual(
            TARGETS["mistral_small_3_2_24b"]["transport"], "local_vllm"
        )
        self.assertEqual(TARGETS["phi4"]["transport"], "local_vllm")

    def test_gpt5_reasoning_request_omits_temperature(self):
        request = chat_request(
            "test", "gpt-5.4-mini", [{"role": "user", "content": "test"}],
            max_tokens=128, temperature=0,
        )
        body = request["body"]
        self.assertEqual(body["max_completion_tokens"], 128)
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertNotIn("max_tokens", body)
        self.assertNotIn("temperature", body)

    def test_gpt5_batch_price_is_registered(self):
        self.assertEqual(model_family("gpt-5.4-mini"), "gpt-5.4-mini")
        self.assertEqual(BATCH_PRICES_PER_MILLION["gpt-5.4-mini"]["input"], 0.75)


if __name__ == "__main__":
    unittest.main()

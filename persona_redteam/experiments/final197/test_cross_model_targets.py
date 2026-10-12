import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from experiments.final197 import evaluate_best_short_cross_model
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
        self.assertEqual(
            TARGETS["llama3_1_8b_instruct"]["model"],
            "meta-llama/Llama-3.1-8B-Instruct",
        )

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

    def test_merge_uses_lanes_recorded_by_launch_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = root / "campaign"
            result = root / "result"
            merged = result / "merged"
            scoring = campaign / "scoring"
            campaign.mkdir()
            (campaign / "launch_manifest.json").write_text(json.dumps({
                "jobs": [{"lane": 0}, {"lane": 1}],
            }), encoding="utf-8")
            for lane in range(2):
                lane_dir = result / f"lane_{lane}"
                lane_dir.mkdir(parents=True)
                (lane_dir / "run_summary.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(
                evaluate_best_short_cross_model, "roots",
                return_value=(campaign, result, merged, scoring),
            ), mock.patch.object(
                evaluate_best_short_cross_model, "merge_shards"
            ) as merge_shards:
                evaluate_best_short_cross_model.merge("campaign", "phi4")
            lane_dirs, output, expected = merge_shards.call_args.args
            self.assertEqual(lane_dirs, [result / "lane_0", result / "lane_1"])
            self.assertEqual(output, merged)
            self.assertEqual(expected, 197)


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import tempfile
import unittest

from experiments.run_manifestation_prompt_pack import MODELS, run


ROOT = Path(__file__).resolve().parents[1]


class ManifestationRunnerTest(unittest.TestCase):
    def test_shared_prefix_and_research_checkpoint_are_not_repeated(self):
        case = json.loads((ROOT / "experiments/fixtures/canonical_manifestation_conversation.json").read_text())
        calls = []

        def fake_complete(model, messages, max_tokens):
            calls.append((model, messages[-1]["content"]))
            return {"text": "안전한 합성 응답", "model": model, "finish_reason": "stop", "usage": {}}

        import experiments.run_manifestation_prompt_pack as module
        original = module.complete
        module.complete = fake_complete
        try:
            with tempfile.TemporaryDirectory() as temp:
                result = run(case, Path(temp) / "result.json")
        finally:
            module.complete = original
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["events"]), 40)
        self.assertEqual(len(calls), 40)
        for model in MODELS:
            stages = [x["stage"] for x in result["events"] if x["model"] == model]
            self.assertEqual(sum(x.startswith("PREFIX_") for x in stages), 6)
            self.assertEqual(sum(x.startswith("RESEARCH_") for x in stages), 3)
            self.assertTrue(all(x in stages for x in ("M3_FINAL", "M4_FINAL", "M5_FINAL", "M6_FINAL")))


if __name__ == "__main__":
    unittest.main()

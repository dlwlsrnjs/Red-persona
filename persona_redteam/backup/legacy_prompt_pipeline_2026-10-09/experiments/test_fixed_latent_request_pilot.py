import json
from pathlib import Path
import unittest

from experiments.fixed_latent_request_pilot import frozen_turns


class FixedLatentRequestPilotTest(unittest.TestCase):
    def test_scripts_are_fixed_five_turn_histories(self):
        cases = json.loads((Path(__file__).parent / "fixtures/fixed_latent_request_samples.json").read_text())
        scripts = [frozen_turns(x) for x in cases]
        self.assertTrue(all(len(x) == 5 for x in scripts))
        self.assertTrue(all("잠재 요청" in x[3] and "직접 답하지 마세요" in x[4] for x in scripts))

    def test_cases_share_identical_analysis_and_response_turns(self):
        cases = json.loads((Path(__file__).parent / "fixtures/fixed_latent_request_samples.json").read_text())
        scripts = [frozen_turns(x) for x in cases]
        self.assertEqual(len({x[3] for x in scripts}), 1)
        self.assertEqual(len({x[4] for x in scripts}), 1)


if __name__ == "__main__":
    unittest.main()

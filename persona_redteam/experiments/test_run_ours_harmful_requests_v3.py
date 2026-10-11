import unittest

from experiments.run_ours_harmful_requests_v3 import canonical_argv


class RunOursHarmfulRequestsV3Test(unittest.TestCase):
    def test_canonical_runner_enables_attack_and_strict_contract(self):
        argv = canonical_argv(["--cases", "cases.json", "--output-dir", "out"])
        self.assertIn("--require-strict-harmful-goal-v3", argv)
        self.assertNotIn("--final-response-only", argv)
        self.assertEqual(argv[argv.index("--condition") + 1], "neutral")
        self.assertEqual(
            argv[argv.index("--final-readout-protocol") + 1],
            "jargon_history_bridge_v1",
        )

    def test_canonical_runner_rejects_endpoint_override(self):
        with self.assertRaisesRegex(ValueError, "locks these arguments"):
            canonical_argv(["--final-response-only"])


if __name__ == "__main__":
    unittest.main()

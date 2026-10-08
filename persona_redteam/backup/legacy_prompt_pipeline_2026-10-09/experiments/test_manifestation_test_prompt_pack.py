import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ManifestationPromptPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads((ROOT / "configs/manifestation_test_prompt_pack.json").read_text())

    def test_seven_conditions_and_shared_history(self):
        self.assertEqual(set(self.pack["conditions"]), {f"M{i}" for i in range(7)})
        self.assertEqual(self.pack["common_history_turns"], [f"H{i}" for i in range(1, 7)])

    def test_only_direct_and_research_conditions_see_goal(self):
        visible = {key for key, value in self.pack["conditions"].items() if value["goal_visible"]}
        self.assertEqual(visible, {"M0", "M3", "M4", "M5", "M6"})

    def test_final_frames_are_independent_and_contrasts_registered(self):
        frames = [value["final_frame"] for value in self.pack["conditions"].values()]
        self.assertEqual(len(frames), len(set(frames)))
        self.assertEqual(len(self.pack["primary_contrasts"]), 6)
        self.assertTrue(self.pack["fixed_controls"]["one_final_frame_per_branch"])


if __name__ == "__main__":
    unittest.main()

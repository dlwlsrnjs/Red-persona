import json
from pathlib import Path
import tempfile
import unittest

from experiments.final197.repair_distributed_goal_anchor import reopen_case


class DistributedGoalAnchorRepairTest(unittest.TestCase):
    def test_reopens_only_selected_latent_turn_and_archives_downstream(self):
        with tempfile.TemporaryDirectory() as root:
            campaign = Path(root) / "campaign"
            output = Path(root) / "output"
            (campaign / "waves").mkdir(parents=True)
            (campaign / "openai_batches/generation-stage-07-latent_goal").mkdir(
                parents=True
            )
            output.mkdir()
            state = {
                "history": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "latent question"},
                    {"role": "assistant", "content": "latent answer"},
                ],
                "dialogue": [
                    ["Researcher", "initial"],
                    ["Researcher", "latent question"],
                    ["Target", "latent answer"],
                ],
                "turns": [{
                    "stage": "latent_goal",
                    "question": "latent question",
                    "target": {"text": "latent answer"},
                }],
                "research_stop": {"after_stage": "latent_goal"},
            }
            (campaign / "research_states.json").write_text(
                json.dumps({"case": {"neutral": state}}), encoding="utf-8"
            )
            (campaign / "waves/stage-07-latent_goal.json").write_text(
                "[]", encoding="utf-8"
            )
            (campaign / "jargon_history_bridge_v1_final_branches.json").write_text(
                "{}", encoding="utf-8"
            )
            (output / "case.json").write_text("{}", encoding="utf-8")
            (output / "run_summary.json").write_text("{}", encoding="utf-8")

            manifest = reopen_case(
                campaign,
                "case",
                repair_id="test_repair",
                archive_downstream=True,
                output_dir=output,
            )

            updated = json.loads(
                (campaign / "research_states.json").read_text(encoding="utf-8")
            )["case"]["neutral"]
            self.assertEqual(updated["turns"], [])
            self.assertEqual(updated["history"], [{"role": "system", "content": "system"}])
            self.assertEqual(updated["dialogue"], [["Researcher", "initial"]])
            self.assertNotIn("research_stop", updated)
            self.assertEqual(updated["goal_recovery_repairs"][0]["repair"], "test_repair")
            self.assertTrue(Path(manifest["backup_state"]).exists())
            self.assertTrue(Path(manifest["archived_wave"]).exists())
            self.assertTrue(Path(manifest["archived_batch"]).exists())
            self.assertFalse((output / "case.json").exists())
            self.assertGreaterEqual(len(manifest["archived_downstream"]), 3)


if __name__ == "__main__":
    unittest.main()

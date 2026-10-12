from __future__ import annotations

import unittest

from .full_history_specificity_pilot import (
    FOLLOWUPS,
    build_candidate_messages,
    select_contentful_seed,
)


class FullHistorySpecificityPilotTest(unittest.TestCase):
    def test_seed_selection_is_content_based_and_metric_blind(self) -> None:
        branches = [
            {"index": 0, "response": "short useful", "scoring_row": {"cares": "Accept"}},
            {"index": 1, "response": "I can't help with that request.", "scoring_row": {}},
            {"index": 2, "response": "a substantially longer useful prior answer", "scoring_row": {}},
            {"index": 3, "response": "tiny", "scoring_row": {}},
        ]
        self.assertEqual(select_contentful_seed(branches)["index"], 2)

    def test_all_candidates_append_same_prior_answer_and_one_followup(self) -> None:
        history = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "earlier answer"},
            {"role": "user", "content": "attack question"},
        ]
        seed = {
            "prompt": "attack question",
            "response": "stored singleton answer",
            "full_messages": history,
        }
        private_goal = "PRIVATE STRING THAT MUST NOT LEAK"
        candidates = build_candidate_messages(seed, private_goal)
        self.assertEqual(len(candidates), len(FOLLOWUPS))
        self.assertEqual(len({row["strategy"] for row in candidates}), 4)
        for candidate in candidates:
            self.assertEqual(candidate["messages"][:-2], history)
            self.assertEqual(
                candidate["messages"][-2],
                {"role": "assistant", "content": "stored singleton answer"},
            )
            self.assertEqual(candidate["messages"][-1]["role"], "user")
            self.assertNotIn(private_goal, candidate["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()

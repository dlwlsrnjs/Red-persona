from __future__ import annotations

import unittest

from .catalog import Catalog
from .protocols import create_session


class InteractiveLabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = Catalog()

    def test_catalog_indexes_final197_and_scored_outcomes(self) -> None:
        self.assertEqual(len(self.catalog.ids()), 197)
        successes = self.catalog.list_cases(outcome="success")
        failures = self.catalog.list_cases(outcome="failure")
        self.assertTrue(successes)
        self.assertTrue(failures)
        self.assertEqual(len(successes) + len(failures), 197)

    def test_case_exposes_persona_history_questions_and_selection(self) -> None:
        case = self.catalog.get_case(self.catalog.ids()[0])
        self.assertTrue(case["goal"])
        self.assertTrue(case["persona"])
        self.assertTrue(case["persona_history"])
        self.assertTrue(case["question_pool"].get("candidates"))
        self.assertIn("selected", case["persona_selection"])

    def test_compact_is_explicit_three_step_state_machine(self) -> None:
        case_id = self.catalog.ids()[0]
        session = create_session(self.catalog, {
            "case_id": case_id,
            "protocol": "red_persona_compact",
            "history_enabled": True,
            "branch_index": 0,
        })
        initial = session.prepare()
        self.assertEqual(initial["stage"], "initial_analysis")
        session.record_response(
            {"text": "The record suggests a focused request.", "provider": "mock", "model": "mock"},
            sent_messages=initial["messages"],
        )
        followup = session.prepare()
        self.assertEqual(followup["stage"], "focused_readout")
        readout = "The persona is asking the assistant to provide a concrete list with the stated constraints."
        session.record_response(
            {"text": readout, "provider": "mock", "model": "mock"},
            sent_messages=followup["messages"],
        )
        final = session.prepare()
        self.assertEqual(final["stage"], "final_query")
        self.assertIn(final["selection"]["selected_quote"], readout)
        self.assertTrue(final["requires_explicit_send"])

    def test_custom_goal_applies_to_direct_baseline(self) -> None:
        session = create_session(self.catalog, {
            "case_id": self.catalog.ids()[0],
            "protocol": "direct_baseline",
            "custom_goal": "custom audit query",
        })
        self.assertEqual(session.prepare()["prompt"], "custom audit query")


if __name__ == "__main__":
    unittest.main()

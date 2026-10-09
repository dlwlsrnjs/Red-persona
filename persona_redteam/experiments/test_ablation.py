import json
import unittest
from unittest.mock import patch

from ablation.aggregate import exact_mcnemar, paired_comparison, parse_evaluations
from ablation.context import transform_case
from ablation.contracts import validate_ablation_run
from ablation.direction_attribution import attribution
from ablation.metrics import METRICS
from ablation.specs import get_spec
from experiments.qwen_target_persona_research_dialogue import (
    FINAL_DIRECTIONS, LEGACY_FINAL_READOUT_PROTOCOL, initial_prompt,
    run_all_conditions_batched,
)


def fixture_case():
    return {
        "case_id": "case-1",
        "crisis_label": "anxiety_crisis",
        "original_request": "private goal",
        "persona": "final persona narrative",
        "metaphor": "a foggy bridge",
        "persona_history": [
            {"user": "client one", "assistant": "counselor one",
             "persona_state": {"summary": "state one"}},
            {"user": "client two", "assistant": "counselor two",
             "persona_state": {"summary": "state two"}},
        ],
    }


class FakeResearcher:
    batch_size = 32

    def questions_batch(self, requests):
        return [(request.get("fallback", "What follows?"), {"source": "fixture"})
                for request in requests]


def fake_complete(model, messages, **kwargs):
    text = (json.dumps({"candidate_response": "candidate", "research_analysis": "analysis"})
            if kwargs.get("json_mode") else "target analysis")
    return {"text": text, "model": model, "finish_reason": "stop", "usage": {}}


class AblationTest(unittest.TestCase):
    def test_dialogue_only_removes_summary_metaphor_and_states(self):
        case = transform_case(fixture_case(), get_spec("dialogue_only"))

        prompt = initial_prompt(case)

        self.assertIn("client one", prompt)
        self.assertIn("counselor two", prompt)
        self.assertIn("Withheld by registered ablation", prompt)
        self.assertNotIn("final persona narrative", prompt)
        self.assertNotIn("foggy bridge", prompt)
        self.assertNotIn("state one", prompt)

    def test_no_prior_dialogue_keeps_persona_and_metaphor(self):
        case = transform_case(fixture_case(), get_spec("no_prior_dialogue"))

        prompt = initial_prompt(case)

        self.assertIn("final persona narrative", prompt)
        self.assertIn("a foggy bridge", prompt)
        self.assertIn("No prior dialogue", prompt)
        self.assertNotIn("client one", prompt)

    @patch("experiments.qwen_target_persona_research_dialogue.complete", side_effect=fake_complete)
    def test_no_research_dialogue_still_runs_four_directions(self, _complete):
        spec = get_spec("no_research_dialogue")
        case = transform_case(fixture_case(), spec)

        results = run_all_conditions_batched(
            case, "fixture-model", FakeResearcher(), target_workers=4,
            research_stage_limit=spec.research_stage_limit,
            enable_dynamic_stop=spec.enable_dynamic_stop,
        )
        record = {"ablation": spec.metadata(), "case": case, "results": results}

        self.assertEqual(len(results), 3)
        self.assertTrue(all(len(result["turns"]) == 1 for result in results))
        self.assertTrue(all(len(result["final_branches"]) == 4 for result in results))
        self.assertTrue(all(
            result["final_readout_protocol"] == LEGACY_FINAL_READOUT_PROTOCOL
            for result in results
        ))
        self.assertTrue(all(
            result["research_stop"]["reason"] == "ablation_no_research_dialogue"
            for result in results
        ))
        self.assertEqual(validate_ablation_run(record), [])

    @patch("experiments.qwen_target_persona_research_dialogue.complete", side_effect=fake_complete)
    def test_fixed_four_runs_exactly_four_research_turns(self, _complete):
        spec = get_spec("fixed_four_research_turns")
        results = run_all_conditions_batched(
            fixture_case(), "fixture-model", FakeResearcher(), target_workers=4,
            research_stage_limit=spec.research_stage_limit,
            enable_dynamic_stop=spec.enable_dynamic_stop,
        )

        self.assertTrue(all(len(result["turns"]) == 5 for result in results))
        self.assertTrue(all(
            result["research_stop"]["reason"] == "ablation_fixed_research_length"
            for result in results
        ))

    def test_paired_comparison_reports_micro_and_equal_category_macro(self):
        def record(category, success):
            return {"crisis_label": category, "outcomes": {
                condition: {metric: success for metric in METRICS}
                for condition in ("neutral", "structural_hint", "oracle_hint")
            }}
        baseline = {"a": record("large", True), "b": record("small", True)}
        variant = {"a": record("large", False), "b": record("small", True)}

        comparison = paired_comparison(baseline, variant)
        row = comparison["comparisons"]["neutral"]["raw_success_at_4"]

        self.assertEqual(row["contribution_micro_delta"], 0.5)
        self.assertEqual(row["contribution_macro_equal_category_delta"], 0.5)
        self.assertEqual(row["baseline_only_successes"], 1)
        self.assertEqual(exact_mcnemar(1, 0), 1.0)

    def test_paired_comparison_accepts_neutral_only_runs(self):
        def record(success):
            return {"crisis_label": "category", "outcomes": {
                "neutral": {metric: success for metric in METRICS}
            }}

        comparison = paired_comparison(
            {"a": record(True)}, {"a": record(False)}
        )

        self.assertEqual(set(comparison["comparisons"]), {"neutral"})
        self.assertEqual(
            comparison["comparisons"]["neutral"]["raw_success_at_4"]
            ["contribution_micro_delta"],
            1.0,
        )

    def test_parse_evaluations_allows_multiple_directories_per_variant(self):
        parsed = parse_evaluations(["full=one", "full=two", "ablated=three"])

        self.assertEqual([str(path) for path in parsed["full"]], ["one", "two"])

    def test_direction_shapley_credit_adds_to_success_at_four(self):
        directions = list(FINAL_DIRECTIONS)

        def record(successful):
            branch_values = {direction: direction in successful for direction in directions}
            return {"crisis_label": "category", "branches": {
                condition: {metric: dict(branch_values) for metric in METRICS}
                for condition in ("neutral", "structural_hint", "oracle_hint")
            }}
        records = {
            "one": record({directions[0]}),
            "two": record({directions[0], directions[1]}),
        }

        row = attribution(records, records)["neutral"]["raw_success_at_4"]

        self.assertEqual(row["full_success_at_4_rate"], 1.0)
        self.assertEqual(row["directions"][directions[0]]["unique_contribution_rate"], 0.5)
        self.assertEqual(row["directions"][directions[0]]["or_shapley_rate"], 0.75)
        self.assertEqual(row["directions"][directions[1]]["or_shapley_rate"], 0.25)
        self.assertEqual(row["shapley_additivity_check"], 1.0)

    def test_direction_attribution_accepts_official_neutral_only_matrix(self):
        directions = list(FINAL_DIRECTIONS)
        branch_values = {
            direction: direction == directions[0] for direction in directions
        }
        records = {"one": {
            "crisis_label": "category",
            "branches": {"neutral": {
                metric: dict(branch_values) for metric in METRICS
            }},
        }}

        result = attribution(records, records)

        self.assertEqual(set(result), {"neutral"})
        self.assertEqual(result["neutral"]["raw_success_at_4"]
                         ["full_success_at_4_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()

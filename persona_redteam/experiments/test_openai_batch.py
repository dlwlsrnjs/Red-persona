import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.run_jmir_persona_batch_api import selected_cases
from pipeline.openai_batch import (
    BatchChatClient,
    chat_request,
    model_family,
    response_record,
)


class OpenAIBatchHelpersTest(unittest.TestCase):
    def test_chat_request_uses_chat_completions_batch_schema(self):
        request = chat_request(
            "case-1", "gpt-4o-2024-11-20",
            [{"role": "user", "content": "hello"}],
            max_tokens=32, json_mode=True,
        )

        self.assertEqual(request["custom_id"], "case-1")
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["url"], "/v1/chat/completions")
        self.assertEqual(request["body"]["response_format"], {"type": "json_object"})

    def test_response_record_preserves_usage_and_request_identity(self):
        record = response_record({
            "id": "chatcmpl-1",
            "model": "gpt-4o-2024-11-20",
            "choices": [{"message": {"content": "answer"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        })

        self.assertEqual(record["text"], "answer")
        self.assertEqual(record["request_id"], "chatcmpl-1")
        self.assertEqual(record["usage"]["completion_tokens"], 4)

    def test_response_record_rejects_empty_or_refused_content(self):
        with self.assertRaises(ValueError):
            response_record({
                "choices": [{"message": {"content": ""},
                             "finish_reason": "content_filter"}],
            })

    def test_actual_cost_uses_batch_prices_and_cached_discount(self):
        cost = BatchChatClient._actual_cost({
            "a": {
                "model": "gpt-4o-2024-11-20",
                "usage": {
                    "prompt_tokens": 1_000_000,
                    "prompt_tokens_details": {"cached_tokens": 200_000},
                    "completion_tokens": 100_000,
                },
            },
            "b": {
                "model": "gpt-4o-mini-2024-07-18",
                "usage": {
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 1_000_000,
                },
            },
        })

        self.assertAlmostEqual(cost, 1.0 + 0.125 + 0.5 + 0.075 + 0.3)
        self.assertEqual(model_family("gpt-4o-mini-2024-07-18"), "gpt-4o-mini")
        self.assertEqual(model_family("gpt-4o-2024-11-20"), "gpt-4o")

    def test_selection_replaces_invalid_cases_instead_of_counting_them(self):
        cases = [
            {"case_id": "existing"},
            {"case_id": "leaking"},
            {"case_id": "replacement"},
        ]
        existing_record = {"case": cases[0], "results": []}

        def active_errors(rows):
            return ["private goal leaked"] if rows[0]["case_id"] == "leaking" else []

        with tempfile.TemporaryDirectory() as directory, patch(
            "experiments.run_jmir_persona_batch_api.run_artifacts",
            return_value=iter([(Path("existing.json"), existing_record)]),
        ), patch(
            "experiments.run_jmir_persona_batch_api.validate_active_cases",
            side_effect=active_errors,
        ), patch(
            "experiments.run_jmir_persona_batch_api.validate_success_at_4_run_record",
            return_value=[],
        ):
            selection_path = Path(directory) / "selection.json"
            selected = selected_cases(cases, [Path("runs")], 2, selection_path)
            manifest = json.loads(selection_path.read_text(encoding="utf-8"))

        self.assertEqual([case["case_id"] for _, case in selected], ["replacement"])
        self.assertEqual(manifest["valid_existing_cases"], 1)
        self.assertEqual(manifest["excluded_input_case_ids"], ["leaking"])


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pipeline.openai_batch import BatchChatClient


class InvalidSuccessResponseTests(unittest.TestCase):
    @patch("pipeline.openai_batch.OpenAI")
    def test_empty_http_200_row_is_recorded_for_retry(self, openai):
        def output(custom_id, content):
            return {
                "custom_id": custom_id,
                "response": {
                    "status_code": 200,
                    "body": {
                        "id": f"response-{custom_id}", "model": "gpt-6-luna",
                        "choices": [{
                            "message": {"content": content},
                            "finish_reason": "stop",
                        }],
                        "usage": {},
                    },
                },
            }

        payload = "\n".join(json.dumps(row) for row in (
            output("valid", "answer"), output("empty", ""),
        )).encode("utf-8")
        api = openai.return_value
        api.files.create.return_value = MagicMock(id="input")
        api.files.content.return_value = payload
        api.batches.create.return_value = MagicMock(
            id="batch", status="validating"
        )
        api.batches.retrieve.return_value = MagicMock(
            status="completed",
            request_counts=MagicMock(completed=2, failed=0),
            output_file_id="output", error_file_id=None,
        )
        requests = [{
            "custom_id": custom_id, "method": "POST",
            "url": "/v1/chat/completions",
            "body": {"model": "gpt-6-luna", "messages": []},
        } for custom_id in ("valid", "empty")]

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}), \
                tempfile.TemporaryDirectory() as directory:
            client = BatchChatClient(directory, max_budget_usd=1)
            with patch.object(client, "estimate_upper_cost", return_value=0):
                result = client._run_once_attempt("generation", requests)
            errors = json.loads((
                Path(directory) / "generation/request_errors.json"
            ).read_text(encoding="utf-8"))

        self.assertEqual(set(result), {"valid"})
        self.assertEqual(errors["empty"]["code"], "invalid_success_response")


if __name__ == "__main__":
    unittest.main()

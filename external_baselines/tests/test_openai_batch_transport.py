import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "openai_batch_transport.py"
SPEC = importlib.util.spec_from_file_location("openai_batch_transport", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeFiles:
    def __init__(self):
        self.input_records = []

    async def create(self, *, file, purpose):
        assert purpose == "batch"
        self.input_records = [json.loads(line) for line in file.read().decode().splitlines()]
        return SimpleNamespace(id="file-input")

    async def content(self, file_id):
        assert file_id == "file-output"
        records = [
            {
                "custom_id": item["custom_id"],
                "response": {
                    "status_code": 200,
                    "body": {
                        "id": item["custom_id"],
                        "model": item["body"]["model"],
                        "choices": [{
                            "finish_reason": "stop",
                            "message": {"content": "ok"},
                        }],
                    },
                },
                "error": None,
            }
            for item in reversed(self.input_records)
        ]
        return SimpleNamespace(text="\n".join(json.dumps(item) for item in records) + "\n")


class FakeBatches:
    def __init__(self):
        self.created = []

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(id="batch-1", status="validating")

    async def retrieve(self, batch_id):
        assert batch_id == "batch-1"
        return SimpleNamespace(
            id=batch_id,
            status="completed",
            output_file_id="file-output",
            error_file_id=None,
        )


class MultiWaveFiles:
    def __init__(self):
        self.inputs = {}
        self.outputs = {}
        self.created_count = 0

    async def create(self, *, file, purpose):
        assert purpose == "batch"
        self.created_count += 1
        file_id = f"file-input-{self.created_count}"
        self.inputs[file_id] = [
            json.loads(line) for line in file.read().decode().splitlines()
        ]
        return SimpleNamespace(id=file_id)

    async def content(self, file_id):
        records = self.outputs[file_id]
        return SimpleNamespace(
            text="\n".join(json.dumps(item) for item in records) + "\n"
        )


class MultiWaveBatches:
    def __init__(self, files):
        self.files = files
        self.created = []
        self.input_by_batch = {}

    async def create(self, **kwargs):
        batch_id = f"batch-{len(self.created) + 1}"
        self.created.append(kwargs)
        self.input_by_batch[batch_id] = kwargs["input_file_id"]
        return SimpleNamespace(id=batch_id, status="validating")

    async def retrieve(self, batch_id):
        input_file_id = self.input_by_batch[batch_id]
        output_file_id = input_file_id.replace("input", "output")
        records = []
        for item in self.files.inputs[input_file_id]:
            last_user_message = item["body"]["messages"][-1]["content"]
            records.append(
                {
                    "custom_id": item["custom_id"],
                    "response": {
                        "status_code": 200,
                        "body": {
                            "id": item["custom_id"],
                            "model": item["body"]["model"],
                            "reply": f"answer:{last_user_message}",
                            "choices": [{
                                "finish_reason": "stop",
                                "message": {"content": f"answer:{last_user_message}"},
                            }],
                        },
                    },
                    "error": None,
                }
            )
        self.files.outputs[output_file_id] = records
        return SimpleNamespace(
            id=batch_id,
            status="completed",
            output_file_id=output_file_id,
            error_file_id=None,
        )


class PartialRetryFiles:
    def __init__(self):
        self.inputs = {}
        self.contents = {}
        self.created_count = 0

    async def create(self, *, file, purpose):
        assert purpose == "batch"
        self.created_count += 1
        file_id = f"file-input-{self.created_count}"
        self.inputs[file_id] = [
            json.loads(line) for line in file.read().decode().splitlines()
        ]
        return SimpleNamespace(id=file_id)

    async def content(self, file_id):
        return SimpleNamespace(
            text="\n".join(json.dumps(item) for item in self.contents[file_id]) + "\n"
        )


class PartialRetryBatches:
    def __init__(self, files):
        self.files = files
        self.created = []

    async def create(self, **kwargs):
        batch_number = len(self.created) + 1
        batch_id = f"batch-{batch_number}"
        self.created.append(kwargs)
        records = self.files.inputs[kwargs["input_file_id"]]
        output_file_id = f"file-output-{batch_number}"
        error_file_id = f"file-error-{batch_number}" if batch_number == 1 else None
        if batch_number == 1:
            self.files.contents[output_file_id] = [
                {
                    "custom_id": records[0]["custom_id"],
                    "response": {"status_code": 200, "body": {
                        "answer": "first",
                        "choices": [{
                            "finish_reason": "stop",
                            "message": {"content": "first"},
                        }],
                    }},
                    "error": None,
                }
            ]
            self.files.contents[error_file_id] = [
                {
                    "custom_id": records[1]["custom_id"],
                    "response": None,
                    "error": {"code": "batch_expired", "message": "retry me"},
                }
            ]
        else:
            self.files.contents[output_file_id] = [
                {
                    "custom_id": records[0]["custom_id"],
                    "response": {"status_code": 200, "body": {
                        "answer": "second",
                        "choices": [{
                            "finish_reason": "stop",
                            "message": {"content": "second"},
                        }],
                    }},
                    "error": None,
                }
            ]
        return SimpleNamespace(id=batch_id, status="in_progress")

    async def retrieve(self, batch_id):
        batch_number = int(batch_id.rsplit("-", 1)[1])
        return SimpleNamespace(
            id=batch_id,
            status="expired" if batch_number == 1 else "completed",
            output_file_id=f"file-output-{batch_number}",
            error_file_id=f"file-error-{batch_number}" if batch_number == 1 else None,
        )


class AlwaysMissingBatches:
    def __init__(self):
        self.created = []

    async def create(self, **kwargs):
        batch_id = f"batch-{len(self.created) + 1}"
        self.created.append(kwargs)
        return SimpleNamespace(id=batch_id, status="in_progress")

    async def retrieve(self, batch_id):
        return SimpleNamespace(
            id=batch_id,
            status="completed",
            output_file_id=None,
            error_file_id=None,
        )


def test_dispatcher_coalesces_concurrent_requests_and_maps_by_custom_id(tmp_path):
    client = SimpleNamespace(files=FakeFiles(), batches=FakeBatches())
    dispatcher = MODULE.OpenAIBatchDispatcher(
        client=client,
        work_dir=tmp_path,
        poll_interval_seconds=0,
        flush_interval_seconds=0.01,
    )

    async def run():
        return await asyncio.gather(
            dispatcher.submit({"model": "gpt-4o", "messages": [{"content": "one"}]}),
            dispatcher.submit({"model": "gpt-4o", "messages": [{"content": "two"}]}),
        )

    responses = asyncio.run(run())

    assert len(client.files.input_records) == 2
    assert len({item["custom_id"] for item in client.files.input_records}) == 2
    assert {response["id"] for response in responses} == {
        item["custom_id"] for item in client.files.input_records
    }
    assert client.batches.created[0]["endpoint"] == "/v1/chat/completions"
    manifest = next(tmp_path.glob("wave-*/manifest.json"))
    assert json.loads(manifest.read_text())["status"] == "completed"


def test_two_turn_conversations_run_as_ordered_batch_waves_with_history(tmp_path):
    files = MultiWaveFiles()
    batches = MultiWaveBatches(files)
    client = SimpleNamespace(files=files, batches=batches)
    dispatcher = MODULE.OpenAIBatchDispatcher(
        client=client,
        work_dir=tmp_path,
        poll_interval_seconds=0,
        flush_interval_seconds=0.01,
    )

    async def conversation(case_id):
        messages = [{"role": "user", "content": f"{case_id}-turn-1"}]
        first = await dispatcher.submit({"model": "gpt-4o", "messages": messages})
        messages = [
            *messages,
            {"role": "assistant", "content": first["reply"]},
            {"role": "user", "content": f"{case_id}-turn-2"},
        ]
        second = await dispatcher.submit({"model": "gpt-4o", "messages": messages})
        return first, second

    async def run():
        return await asyncio.gather(
            conversation("case-a"),
            conversation("case-b"),
        )

    results = asyncio.run(run())

    assert len(results) == 2
    assert len(batches.created) == 2
    wave_inputs = [files.inputs[item["input_file_id"]] for item in batches.created]
    assert [len(records) for records in wave_inputs] == [2, 2]
    assert all(len(item["body"]["messages"]) == 1 for item in wave_inputs[0])
    assert all(len(item["body"]["messages"]) == 3 for item in wave_inputs[1])
    second_wave_histories = [item["body"]["messages"] for item in wave_inputs[1]]
    assert {history[1]["content"] for history in second_wave_histories} == {
        "answer:case-a-turn-1",
        "answer:case-b-turn-1",
    }


def test_dispatcher_rejects_streaming_request(tmp_path):
    client = SimpleNamespace(files=FakeFiles(), batches=FakeBatches())
    dispatcher = MODULE.OpenAIBatchDispatcher(client=client, work_dir=tmp_path)

    async def run():
        await dispatcher.submit({"model": "gpt-4o", "stream": True})

    try:
        asyncio.run(run())
    except ValueError as exc:
        assert "stream=true" in str(exc)
    else:
        raise AssertionError("streaming batch request should fail")


def test_dispatcher_retries_only_failed_or_missing_requests(tmp_path):
    files = PartialRetryFiles()
    batches = PartialRetryBatches(files)
    dispatcher = MODULE.OpenAIBatchDispatcher(
        client=SimpleNamespace(files=files, batches=batches),
        work_dir=tmp_path,
        poll_interval_seconds=0,
        flush_interval_seconds=0.01,
        max_request_retries=2,
        retry_backoff_seconds=0,
    )

    async def run():
        return await asyncio.gather(
            dispatcher.submit({"model": "gpt-4o", "messages": [{"content": "one"}]}),
            dispatcher.submit({"model": "gpt-4o", "messages": [{"content": "two"}]}),
        )

    responses = asyncio.run(run())

    assert [response["answer"] for response in responses] == ["first", "second"]
    assert len(batches.created) == 2
    first_input = files.inputs[batches.created[0]["input_file_id"]]
    retry_input = files.inputs[batches.created[1]["input_file_id"]]
    assert len(first_input) == 2
    assert len(retry_input) == 1
    assert retry_input[0]["custom_id"] == first_input[1]["custom_id"]
    manifest = json.loads(next(tmp_path.glob("wave-*/manifest.json")).read_text())
    assert manifest["status"] == "completed"
    assert manifest["successful_results"] == 2
    assert [attempt["request_count"] for attempt in manifest["attempts"]] == [2, 1]


def test_dispatcher_fails_only_after_request_retry_budget_is_exhausted(tmp_path):
    files = PartialRetryFiles()
    batches = AlwaysMissingBatches()
    dispatcher = MODULE.OpenAIBatchDispatcher(
        client=SimpleNamespace(files=files, batches=batches),
        work_dir=tmp_path,
        poll_interval_seconds=0,
        flush_interval_seconds=0,
        max_request_retries=1,
        retry_backoff_seconds=0,
    )

    async def run():
        return await dispatcher.submit(
            {"model": "gpt-4o", "messages": [{"content": "missing"}]}
        )

    with pytest.raises(MODULE.OpenAIBatchRequestError, match="without a result"):
        asyncio.run(run())

    assert len(batches.created) == 2
    manifest = json.loads(next(tmp_path.glob("wave-*/manifest.json")).read_text())
    assert manifest["status"] == "failed"
    assert manifest["failed_results"] == 1

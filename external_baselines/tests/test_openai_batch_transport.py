import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


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
                    "body": {"id": item["custom_id"], "model": item["body"]["model"]},
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

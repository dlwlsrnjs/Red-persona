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

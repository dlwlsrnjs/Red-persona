"""Asynchronous request coalescing for OpenAI's Batch Chat Completions API."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any
from uuid import uuid4


TERMINAL_BATCH_STATES = {"completed", "failed", "expired", "cancelled"}


class OpenAIBatchRequestError(RuntimeError):
    """Raised when a request inside an OpenAI batch does not produce a response."""


@dataclass
class _PendingRequest:
    custom_id: str
    body: dict[str, Any]
    future: asyncio.Future[dict[str, Any]]


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _jsonl_records(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


class OpenAIBatchDispatcher:
    """Collect concurrent chat requests and execute each collected wave as one batch."""

    def __init__(
        self,
        *,
        client: Any,
        work_dir: Path,
        poll_interval_seconds: float = 60.0,
        flush_interval_seconds: float = 1.0,
        max_requests_per_batch: int = 50_000,
    ) -> None:
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be non-negative")
        if flush_interval_seconds < 0:
            raise ValueError("flush_interval_seconds must be non-negative")
        if not 1 <= max_requests_per_batch <= 50_000:
            raise ValueError("max_requests_per_batch must be between 1 and 50000")
        self._client = client
        self._work_dir = work_dir
        self._poll_interval_seconds = poll_interval_seconds
        self._flush_interval_seconds = flush_interval_seconds
        self._max_requests_per_batch = max_requests_per_batch
        self._pending: list[_PendingRequest] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._wave_number = 0

    async def submit(self, body: dict[str, Any]) -> dict[str, Any]:
        """Queue one Chat Completions body and wait for its batch response body."""
        if not body.get("model"):
            raise ValueError("Batch request body must contain a model")
        if body.get("stream") is True:
            raise ValueError("OpenAI Batch API does not support stream=true")
        loop = asyncio.get_running_loop()
        pending = _PendingRequest(
            custom_id=f"request-{uuid4().hex}",
            body=dict(body),
            future=loop.create_future(),
        )
        flush_now = False
        async with self._lock:
            self._pending.append(pending)
            if len(self._pending) >= self._max_requests_per_batch:
                flush_now = True
            elif self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._delayed_flush())
        if flush_now:
            await self._flush()
        return await pending.future

    async def _delayed_flush(self) -> None:
        await asyncio.sleep(self._flush_interval_seconds)
        await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            if not self._pending:
                return
            requests = self._pending[: self._max_requests_per_batch]
            del self._pending[: len(requests)]
            self._wave_number += 1
            wave_number = self._wave_number
            if self._pending:
                self._flush_task = asyncio.create_task(self._delayed_flush())
        asyncio.create_task(self._execute_wave(requests=requests, wave_number=wave_number))

    async def _execute_wave(
        self, *, requests: list[_PendingRequest], wave_number: int
    ) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        wave_dir = self._work_dir / f"wave-{wave_number:04d}-{stamp}-{uuid4().hex[:8]}"
        input_path = wave_dir / "input.jsonl"
        output_path = wave_dir / "output.jsonl"
        error_path = wave_dir / "errors.jsonl"
        manifest_path = wave_dir / "manifest.json"
        wave_dir.mkdir(parents=True, exist_ok=False)
        input_lines = [
            json.dumps(
                {
                    "custom_id": item.custom_id,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": item.body,
                },
                ensure_ascii=False,
                allow_nan=False,
            )
            for item in requests
        ]
        input_path.write_text("\n".join(input_lines) + "\n", encoding="utf-8")
        manifest: dict[str, Any] = {
            "schema_version": "red-persona-openai-batch-v1",
            "wave": wave_number,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request_count": len(requests),
            "models": sorted({str(item.body["model"]) for item in requests}),
            "endpoint": "/v1/chat/completions",
            "completion_window": "24h",
            "status": "uploading",
            "input_path": str(input_path),
        }
        _atomic_json(manifest_path, manifest)

        try:
            if len(manifest["models"]) != 1:
                raise ValueError("Each OpenAI batch input file must contain exactly one model")
            with input_path.open("rb") as handle:
                uploaded = await self._client.files.create(file=handle, purpose="batch")
            batch = await self._client.batches.create(
                input_file_id=uploaded.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
                metadata={"pipeline": "red-persona", "wave": str(wave_number)},
            )
            manifest.update(
                {
                    "input_file_id": uploaded.id,
                    "batch_id": batch.id,
                    "status": str(batch.status),
                }
            )
            _atomic_json(manifest_path, manifest)

            while str(batch.status) not in TERMINAL_BATCH_STATES:
                await asyncio.sleep(self._poll_interval_seconds)
                batch = await self._client.batches.retrieve(batch.id)
                manifest["status"] = str(batch.status)
                manifest["last_checked_at"] = datetime.now(timezone.utc).isoformat()
                _atomic_json(manifest_path, manifest)

            output_records: list[dict[str, Any]] = []
            error_records: list[dict[str, Any]] = []
            if getattr(batch, "output_file_id", None):
                content = await self._client.files.content(batch.output_file_id)
                output_path.write_text(content.text, encoding="utf-8")
                output_records = _jsonl_records(content.text)
            if getattr(batch, "error_file_id", None):
                content = await self._client.files.content(batch.error_file_id)
                error_path.write_text(content.text, encoding="utf-8")
                error_records = _jsonl_records(content.text)

            records = {
                record.get("custom_id"): record
                for record in [*output_records, *error_records]
                if record.get("custom_id")
            }
            for item in requests:
                record = records.get(item.custom_id)
                if record is None:
                    self._set_exception(
                        item,
                        f"Batch {batch.id} ended as {batch.status} without a result for {item.custom_id}",
                    )
                    continue
                response = record.get("response")
                error = record.get("error")
                if error or not response or response.get("status_code") != 200:
                    detail = error or (response or {}).get("body") or record
                    self._set_exception(
                        item,
                        f"Batch request {item.custom_id} failed: {json.dumps(detail, ensure_ascii=False)[:1000]}",
                    )
                    continue
                if not item.future.done():
                    item.future.set_result(response["body"])

            manifest.update(
                {
                    "status": str(batch.status),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "output_file_id": getattr(batch, "output_file_id", None),
                    "error_file_id": getattr(batch, "error_file_id", None),
                    "successful_results": len(output_records),
                    "error_results": len(error_records),
                    "elapsed_seconds": round(time.time() - datetime.fromisoformat(manifest["created_at"]).timestamp(), 3),
                }
            )
            _atomic_json(manifest_path, manifest)
        except Exception as exc:
            manifest.update(
                {
                    "status": "dispatcher_error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _atomic_json(manifest_path, manifest)
            for item in requests:
                if not item.future.done():
                    item.future.set_exception(exc)

    @staticmethod
    def _set_exception(item: _PendingRequest, message: str) -> None:
        if not item.future.done():
            item.future.set_exception(OpenAIBatchRequestError(message))

"""Asynchronous request coalescing for OpenAI's Batch Chat Completions API."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Awaitable, Callable, TypeVar
from uuid import uuid4


TERMINAL_BATCH_STATES = {"completed", "failed", "expired", "cancelled"}
_T = TypeVar("_T")


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
        max_request_retries: int = 2,
        api_call_retries: int = 4,
        retry_backoff_seconds: float = 5.0,
    ) -> None:
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be non-negative")
        if flush_interval_seconds < 0:
            raise ValueError("flush_interval_seconds must be non-negative")
        if not 1 <= max_requests_per_batch <= 50_000:
            raise ValueError("max_requests_per_batch must be between 1 and 50000")
        if max_request_retries < 0:
            raise ValueError("max_request_retries must be non-negative")
        if api_call_retries < 0:
            raise ValueError("api_call_retries must be non-negative")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        self._client = client
        self._work_dir = work_dir
        self._poll_interval_seconds = poll_interval_seconds
        self._flush_interval_seconds = flush_interval_seconds
        self._max_requests_per_batch = max_requests_per_batch
        self._max_request_retries = max_request_retries
        self._api_call_retries = api_call_retries
        self._retry_backoff_seconds = retry_backoff_seconds
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
        manifest_path = wave_dir / "manifest.json"
        wave_dir.mkdir(parents=True, exist_ok=False)
        manifest: dict[str, Any] = {
            "schema_version": "red-persona-openai-batch-v2",
            "wave": wave_number,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request_count": len(requests),
            "models": sorted({str(item.body["model"]) for item in requests}),
            "endpoint": "/v1/chat/completions",
            "completion_window": "24h",
            "status": "running",
            "max_request_attempts": self._max_request_retries + 1,
            "attempts": [],
        }
        _atomic_json(manifest_path, manifest)

        if len(manifest["models"]) != 1:
            exc = ValueError("Each OpenAI batch input file must contain exactly one model")
            for item in requests:
                if not item.future.done():
                    item.future.set_exception(exc)
            manifest.update(status="failed", error_type=type(exc).__name__, error=str(exc))
            _atomic_json(manifest_path, manifest)
            return

        unresolved = list(requests)
        last_errors: dict[str, str] = {}
        for attempt_number in range(1, self._max_request_retries + 2):
            if attempt_number > 1 and self._retry_backoff_seconds:
                await asyncio.sleep(
                    self._retry_backoff_seconds * (2 ** (attempt_number - 2))
                )
            unresolved, attempt_summary, last_errors = await self._execute_attempt(
                requests=unresolved,
                wave_number=wave_number,
                attempt_number=attempt_number,
                attempt_dir=wave_dir / f"attempt-{attempt_number:02d}",
            )
            manifest["attempts"].append(attempt_summary)
            manifest["resolved_count"] = len(requests) - len(unresolved)
            manifest["unresolved_count"] = len(unresolved)
            manifest["last_checked_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_json(manifest_path, manifest)
            if not unresolved:
                break

        for item in unresolved:
            self._set_exception(
                item,
                last_errors.get(
                    item.custom_id,
                    f"Batch request {item.custom_id} remained unresolved after retries",
                ),
            )
        manifest.update(
            {
                "status": "completed" if not unresolved else "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "successful_results": len(requests) - len(unresolved),
                "failed_results": len(unresolved),
                "failed_custom_ids": [item.custom_id for item in unresolved],
                "elapsed_seconds": round(
                    time.time()
                    - datetime.fromisoformat(manifest["created_at"]).timestamp(),
                    3,
                ),
            }
        )
        _atomic_json(manifest_path, manifest)

    async def _execute_attempt(
        self,
        *,
        requests: list[_PendingRequest],
        wave_number: int,
        attempt_number: int,
        attempt_dir: Path,
    ) -> tuple[list[_PendingRequest], dict[str, Any], dict[str, str]]:
        attempt_dir.mkdir(parents=True, exist_ok=False)
        input_path = attempt_dir / "input.jsonl"
        output_path = attempt_dir / "output.jsonl"
        error_path = attempt_dir / "errors.jsonl"
        manifest_path = attempt_dir / "manifest.json"
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
        attempt: dict[str, Any] = {
            "attempt": attempt_number,
            "request_count": len(requests),
            "custom_ids": [item.custom_id for item in requests],
            "status": "uploading",
            "input_path": str(input_path),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "batch_create_idempotency_key": f"red-persona-{uuid4().hex}",
        }
        _atomic_json(manifest_path, attempt)
        try:
            with input_path.open("rb") as handle:
                async def upload_input() -> Any:
                    handle.seek(0)
                    return await self._client.files.create(file=handle, purpose="batch")

                uploaded = await self._api_call(upload_input)
            batch = await self._api_call(
                lambda: self._client.batches.create(
                    input_file_id=uploaded.id,
                    endpoint="/v1/chat/completions",
                    completion_window="24h",
                    metadata={
                        "pipeline": "red-persona",
                        "wave": str(wave_number),
                        "attempt": str(attempt_number),
                    },
                    extra_headers={
                        "Idempotency-Key": attempt["batch_create_idempotency_key"]
                    },
                )
            )
            attempt.update(
                input_file_id=uploaded.id,
                batch_id=batch.id,
                status=self._status(batch),
            )
            _atomic_json(manifest_path, attempt)
            while self._status(batch) not in TERMINAL_BATCH_STATES:
                await asyncio.sleep(self._poll_interval_seconds)
                batch = await self._api_call(
                    lambda: self._client.batches.retrieve(batch.id)
                )
                attempt["status"] = self._status(batch)
                attempt["last_checked_at"] = datetime.now(timezone.utc).isoformat()
                _atomic_json(manifest_path, attempt)

            output_records: list[dict[str, Any]] = []
            error_records: list[dict[str, Any]] = []
            if getattr(batch, "output_file_id", None):
                content = await self._api_call(
                    lambda: self._client.files.content(batch.output_file_id)
                )
                output_path.write_text(content.text, encoding="utf-8")
                output_records = _jsonl_records(content.text)
            if getattr(batch, "error_file_id", None):
                content = await self._api_call(
                    lambda: self._client.files.content(batch.error_file_id)
                )
                error_path.write_text(content.text, encoding="utf-8")
                error_records = _jsonl_records(content.text)

            records = {
                record.get("custom_id"): record
                for record in [*output_records, *error_records]
                if record.get("custom_id")
            }
            unresolved: list[_PendingRequest] = []
            errors: dict[str, str] = {}
            for item in requests:
                record = records.get(item.custom_id)
                if record is None:
                    errors[item.custom_id] = (
                        f"Batch {batch.id} ended as {self._status(batch)} without a "
                        f"result for {item.custom_id}"
                    )
                    unresolved.append(item)
                    continue
                response = record.get("response")
                error = record.get("error")
                if error or not response or response.get("status_code") != 200:
                    detail = error or (response or {}).get("body") or record
                    errors[item.custom_id] = (
                        f"Batch request {item.custom_id} failed: "
                        f"{json.dumps(detail, ensure_ascii=False)[:1000]}"
                    )
                    unresolved.append(item)
                    continue
                choices = (response.get("body") or {}).get("choices") or []
                incomplete_reasons = [
                    str(choice.get("finish_reason"))
                    for choice in choices
                    if choice.get("finish_reason") not in {"stop", "tool_calls"}
                ]
                if not choices or incomplete_reasons:
                    errors[item.custom_id] = (
                        f"Batch request {item.custom_id} returned an incomplete "
                        f"completion: finish_reason={incomplete_reasons or ['missing']}"
                    )
                    unresolved.append(item)
                    continue
                if not item.future.done():
                    item.future.set_result(response["body"])

            attempt.update(
                {
                    "status": self._status(batch),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "output_file_id": getattr(batch, "output_file_id", None),
                    "error_file_id": getattr(batch, "error_file_id", None),
                    "successful_results": len(requests) - len(unresolved),
                    "failed_results": len(unresolved),
                    "retry_custom_ids": [item.custom_id for item in unresolved],
                }
            )
            _atomic_json(manifest_path, attempt)
            return unresolved, dict(attempt), errors
        except Exception as exc:
            message = f"Batch attempt {attempt_number} failed: {type(exc).__name__}: {exc}"
            attempt.update(
                {
                    "status": "dispatcher_error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "successful_results": 0,
                    "failed_results": len(requests),
                    "retry_custom_ids": [item.custom_id for item in requests],
                }
            )
            _atomic_json(manifest_path, attempt)
            return requests, dict(attempt), {
                item.custom_id: message for item in requests
            }

    async def _api_call(self, call: Callable[[], Awaitable[_T]]) -> _T:
        """Retry transient API transport and rate-limit failures."""
        for retry_number in range(self._api_call_retries + 1):
            try:
                return await call()
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                retryable = (
                    status_code is None
                    or status_code in {408, 409, 429}
                    or (isinstance(status_code, int) and status_code >= 500)
                )
                if retry_number >= self._api_call_retries or not retryable:
                    raise
                if self._retry_backoff_seconds:
                    await asyncio.sleep(
                        self._retry_backoff_seconds * (2 ** retry_number)
                    )
        raise AssertionError("unreachable")

    @staticmethod
    def _status(batch: Any) -> str:
        status = getattr(batch, "status", "")
        return str(getattr(status, "value", status)).lower()

    @staticmethod
    def _set_exception(item: _PendingRequest, message: str) -> None:
        if not item.future.done():
            item.future.set_exception(OpenAIBatchRequestError(message))

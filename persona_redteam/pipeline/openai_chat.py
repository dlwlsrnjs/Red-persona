"""Checkpointed parallel OpenAI Chat Completions client for latency-sensitive tails."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import random
import time

from openai import OpenAI

from pipeline.openai_batch import (
    BatchChatClient,
    response_record,
)
from pipeline.runtime_io import atomic_json


def non_retryable_quota_error(exc):
    """Return True for account-credit failures that retries cannot resolve."""
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        body = {}
    nested = body.get("error") if isinstance(body.get("error"), dict) else {}
    code = str(body.get("code") or nested.get("code") or "").lower()
    kind = str(body.get("type") or nested.get("type") or "").lower()
    message = str(exc).lower()
    markers = (
        "credit_balance_exhausted", "insufficient_quota",
        "no credits remaining",
    )
    return any(marker in code or marker in kind or marker in message
               for marker in markers)


class OpenAIChatClient:
    """Run Batch-style request dictionaries through the synchronous endpoint.

    This is reserved for latency-sensitive evaluation tails. Generation remains
    on Batch. Checkpoints and the separate ledger make the API-mode change
    explicit rather than silently mixing synchronous responses into Batch files.
    """

    api_mode = "openai_chat_completions"

    def __init__(self, state_dir, *, workers=128, retries=4,
                 max_budget_usd=5.0):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.workers = max(1, int(workers))
        self.retries = max(0, int(retries))
        self.max_budget_usd = (
            None if max_budget_usd is None else float(max_budget_usd)
        )
        # This client owns the retry loop so SDK retries are disabled.  Keeping
        # only one retry layer avoids multiplying calls and follows the OpenAI
        # rate-limit guidance for high-concurrency synchronous workloads.
        self.client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"], max_retries=0, timeout=60.0
        )
        self.ledger_path = self.state_dir / "usage_ledger.json"

    @staticmethod
    def _input_hash(requests):
        text = "".join(json.dumps(request, ensure_ascii=False, sort_keys=True) + "\n"
                       for request in requests)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _ledger(self):
        if self.ledger_path.exists():
            return json.loads(self.ledger_path.read_text(encoding="utf-8"))
        return {"max_budget_usd": self.max_budget_usd, "calls": {}}

    def actual_cost(self):
        return sum(row["cost_usd"] for row in self._ledger()["calls"].values())

    @staticmethod
    def _actual_cost(results):
        # OpenAI documents Batch as 50% below the synchronous endpoint. Reuse
        # the pinned-model Batch table and multiply by two so both ledgers share
        # the same cached-token accounting.
        return 2.0 * BatchChatClient._actual_cost(results)

    def estimate_upper_cost(self, requests):
        # The same request has a 2x upper estimate outside Batch.
        estimator = object.__new__(BatchChatClient)
        return 2.0 * BatchChatClient.estimate_upper_cost(estimator, requests)

    def _complete(self, request):
        body = request["body"]
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                completion = self.client.chat.completions.create(**body)
                return response_record(completion.model_dump())
            except Exception as exc:  # SDK exception classes vary by release.
                last_error = exc
                if non_retryable_quota_error(exc):
                    raise RuntimeError(
                        "OpenAI account has no usable credit; request was not retried"
                    ) from exc
                if attempt < self.retries:
                    response = getattr(exc, "response", None)
                    headers = getattr(response, "headers", {}) or {}
                    try:
                        retry_after = float(headers.get("retry-after", 0) or 0)
                    except (TypeError, ValueError):
                        retry_after = 0.0
                    delay = max(retry_after, min(0.5 * (2 ** attempt), 8.0))
                    time.sleep(delay + random.uniform(0.0, 0.25))
        raise RuntimeError(
            f"OpenAI request {request['custom_id']} failed: {last_error}"
        )

    def run(self, label, requests, *, retries=2):
        del retries  # Per-request retry count is set on the client.
        ids = [request["custom_id"] for request in requests]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label}: duplicate custom_id")
        label_dir = self.state_dir / label
        label_dir.mkdir(parents=True, exist_ok=True)
        state_path = label_dir / "state.json"
        result_path = label_dir / "results.json"
        partial_path = label_dir / "partial_results.json"
        input_hash = self._input_hash(requests)
        if result_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state["input_sha256"] != input_hash:
                raise RuntimeError(f"{label}: checkpoint input changed")
            return json.loads(result_path.read_text(encoding="utf-8"))

        estimated = self.estimate_upper_cost(requests)
        if (self.max_budget_usd is not None and
                self.actual_cost() + estimated > self.max_budget_usd):
            raise RuntimeError(
                f"budget guard: spent ${self.actual_cost():.4f} + request upper "
                f"estimate ${estimated:.4f} exceeds ${self.max_budget_usd:.2f}"
            )
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state["input_sha256"] != input_hash:
                raise RuntimeError(f"{label}: pending checkpoint input changed")
        else:
            atomic_json(state_path, {
                "label": label,
                "input_sha256": input_hash,
                "requests": len(requests),
                "workers": self.workers,
                "api_mode": self.api_mode,
                "upper_estimated_cost_usd": estimated,
            })
        results = (
            json.loads(partial_path.read_text(encoding="utf-8"))
            if partial_path.exists() else {}
        )
        pending = [request for request in requests
                   if request["custom_id"] not in results]
        errors = {}
        completed_since_checkpoint = 0
        completed_total = len(results)
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=min(self.workers, len(pending) or 1)) as pool:
            futures = {pool.submit(self._complete, request): request["custom_id"]
                       for request in pending}
            for future in as_completed(futures):
                custom_id = futures[future]
                try:
                    results[custom_id] = future.result()
                    completed_since_checkpoint += 1
                    completed_total += 1
                    if completed_since_checkpoint >= 50:
                        atomic_json(partial_path, results)
                        completed_since_checkpoint = 0
                    if completed_total % 100 == 0 or completed_total == len(ids):
                        print(json.dumps({
                            "run": label,
                            "status": "in_progress",
                            "completed": completed_total,
                            "total": len(ids),
                            "failed_so_far": len(errors),
                            "elapsed_seconds": round(time.monotonic() - started, 1),
                        }), flush=True)
                except Exception as exc:
                    errors[custom_id] = {
                        "error_type": type(exc).__name__, "error": str(exc),
                    }
                    if "no usable credit" in str(exc):
                        for pending_future in futures:
                            if pending_future is not future:
                                pending_future.cancel()
                        break
        atomic_json(partial_path, results)
        atomic_json(label_dir / "request_errors.json", errors)
        if errors:
            raise RuntimeError(
                f"{label}: {len(errors)} synchronous requests failed; resume will "
                "retry only missing custom IDs"
            )
        ordered = {custom_id: results[custom_id] for custom_id in ids}
        atomic_json(result_path, ordered)
        cost = self._actual_cost(ordered)
        ledger = self._ledger()
        ledger["max_budget_usd"] = self.max_budget_usd
        ledger["calls"][label] = {
            "requests": len(requests), "completed": len(ordered),
            "failed": 0, "cost_usd": cost,
        }
        atomic_json(self.ledger_path, ledger)
        print(json.dumps({
            "batch": label, "status": "completed", "requests": len(requests),
            "completed": len(ordered), "failed": 0, "api_mode": self.api_mode,
            "cost_usd": cost,
        }), flush=True)
        return ordered

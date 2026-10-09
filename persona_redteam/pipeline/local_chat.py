"""Checkpointed OpenAI-compatible local chat client for vLLM target arms."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

from openai import OpenAI

from pipeline.openai_batch import response_record
from pipeline.runtime_io import atomic_json


class LocalChatClient:
    """Execute Batch-style request dictionaries against a local vLLM server."""

    api_mode = "local_vllm"

    def __init__(self, state_dir, *, base_url, workers=128, retries=3):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        if self.base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0] not in {
            "127.0.0.1", "localhost", "::1",
        }:
            raise ValueError("local target base URL must resolve to localhost")
        self.workers = max(1, int(workers))
        self.retries = max(0, int(retries))
        self.client = OpenAI(base_url=self.base_url, api_key="local")
        self.max_budget_usd = float("inf")

    def actual_cost(self):
        return 0.0

    def estimate_upper_cost(self, requests):
        return 0.0

    @staticmethod
    def _input_hash(requests):
        value = "".join(
            json.dumps(request, ensure_ascii=False, sort_keys=True) + "\n"
            for request in requests
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _complete(self, request):
        body = request["body"]
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                completion = self.client.chat.completions.create(**body)
                payload = completion.model_dump()
                return response_record(payload)
            except Exception as exc:  # SDK exception types vary by version.
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(0.5 * (2 ** attempt), 4.0))
        raise RuntimeError(
            f"local target request {request['custom_id']} failed: {last_error}"
        )

    def run(self, label, requests, *, retries=2):
        del retries  # Per-request retries are configured on the client.
        ids = [request["custom_id"] for request in requests]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label}: duplicate custom_id")
        label_dir = self.state_dir / label
        label_dir.mkdir(parents=True, exist_ok=True)
        state_path = label_dir / "state.json"
        result_path = label_dir / "results.json"
        input_hash = self._input_hash(requests)
        if result_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state["input_sha256"] != input_hash:
                raise RuntimeError(f"{label}: checkpoint input changed")
            return json.loads(result_path.read_text(encoding="utf-8"))

        atomic_json(state_path, {
            "label": label,
            "input_sha256": input_hash,
            "requests": len(requests),
            "base_url": self.base_url,
            "workers": self.workers,
        })
        results = {}
        errors = {}
        with ThreadPoolExecutor(max_workers=min(self.workers, len(requests) or 1)) as pool:
            futures = {pool.submit(self._complete, request): request["custom_id"]
                       for request in requests}
            for future in as_completed(futures):
                custom_id = futures[future]
                try:
                    results[custom_id] = future.result()
                except Exception as exc:
                    errors[custom_id] = {
                        "error_type": type(exc).__name__, "error": str(exc),
                    }
        atomic_json(label_dir / "request_errors.json", errors)
        if errors:
            raise RuntimeError(
                f"{label}: {len(errors)} local target requests failed; checkpoint not sealed"
            )
        ordered = {custom_id: results[custom_id] for custom_id in ids}
        atomic_json(result_path, ordered)
        print(json.dumps({
            "batch": label, "status": "completed", "requests": len(requests),
            "completed": len(ordered), "failed": 0, "api_mode": "local_vllm",
        }), flush=True)
        return ordered

"""Checkpointed OpenAI Batch API client with a hard pre-submission budget guard."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

from openai import NotFoundError, OpenAI
import tiktoken

from pipeline.runtime_io import atomic_json


TERMINAL_FAILURES = {"failed", "expired", "cancelled"}
BATCH_PRICES_PER_MILLION = {
    "gpt-4o": {"input": 1.25, "cached": 0.625, "output": 5.00},
    "gpt-4o-mini": {"input": 0.075, "cached": 0.0375, "output": 0.30},
}


def model_family(model):
    return "gpt-4o-mini" if model.startswith("gpt-4o-mini") else "gpt-4o"


def response_record(body):
    choice = body["choices"][0]
    text = choice["message"].get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            f"empty batch completion or refused (finish={choice.get('finish_reason')})"
        )
    return {
        "text": text,
        "model": body.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": body.get("usage", {}),
        "request_id": body.get("id"),
        "revision": body.get("revision"),
        "system_fingerprint": body.get("system_fingerprint"),
    }


class BatchChatClient:
    api_mode = "openai_batch"

    def __init__(self, state_dir, *, max_budget_usd=120.0, poll_seconds=20):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.max_budget_usd = (
            None if max_budget_usd is None else float(max_budget_usd)
        )
        self.poll_seconds = max(5, int(poll_seconds))
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.ledger_path = self.state_dir / "usage_ledger.json"

    def _ledger(self):
        if self.ledger_path.exists():
            return json.loads(self.ledger_path.read_text(encoding="utf-8"))
        return {"max_budget_usd": self.max_budget_usd, "batches": {}}

    def actual_cost(self):
        return sum(row["cost_usd"] for row in self._ledger()["batches"].values())

    @staticmethod
    def _encoding(model):
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            return tiktoken.get_encoding("o200k_base")

    def estimate_upper_cost(self, requests):
        total = 0.0
        encodings = {}
        for request in requests:
            body = request["body"]
            model = body["model"]
            encoding = encodings.setdefault(model, self._encoding(model))
            prompt_tokens = 20
            for message in body["messages"]:
                prompt_tokens += 10 + len(encoding.encode(str(message.get("content", ""))))
            # Some published protocols intentionally omit the completion cap and
            # rely on the API default.  Keep that field absent from the wire
            # request, but require an explicit accounting assumption so the
            # preflight budget estimate never silently treats it as zero.
            output_tokens = body.get(
                "max_tokens",
                body.get(
                    "max_completion_tokens",
                    request.get("estimated_output_tokens", 1024),
                ),
            )
            price = BATCH_PRICES_PER_MILLION[model_family(model)]
            total += (prompt_tokens * price["input"] + output_tokens * price["output"]) / 1e6
        return total * 1.10

    @staticmethod
    def _actual_cost(results):
        total = 0.0
        for result in results.values():
            usage = result.get("usage", {})
            prompt = usage.get("prompt_tokens", 0) or 0
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
            completion = usage.get("completion_tokens", 0) or 0
            price = BATCH_PRICES_PER_MILLION[model_family(result.get("model", "gpt-4o"))]
            total += ((prompt - cached) * price["input"] + cached * price["cached"] +
                      completion * price["output"]) / 1e6
        return total

    @staticmethod
    def _content_bytes(content):
        if hasattr(content, "read"):
            value = content.read()
        else:
            value = getattr(content, "content", content)
        if isinstance(value, str):
            return value.encode("utf-8")
        return value

    def _run_once(self, label, requests):
        label_dir = self.state_dir / label
        label_dir.mkdir(parents=True, exist_ok=True)
        input_path = label_dir / "input.jsonl"
        state_path = label_dir / "state.json"
        result_path = label_dir / "results.json"
        input_text = "".join(
            json.dumps(
                {key: value for key, value in request.items()
                 if key != "estimated_output_tokens"},
                ensure_ascii=False,
            ) + "\n"
            for request in requests
        )
        input_hash = hashlib.sha256(input_text.encode("utf-8")).hexdigest()

        if result_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state["input_sha256"] != input_hash:
                raise RuntimeError(f"{label}: checkpoint input changed")
            return json.loads(result_path.read_text(encoding="utf-8"))

        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state["input_sha256"] != input_hash:
                raise RuntimeError(f"{label}: pending checkpoint input changed")
            batch_id = state["batch_id"]
        else:
            estimated = self.estimate_upper_cost(requests)
            spent = self.actual_cost()
            if (self.max_budget_usd is not None and
                    spent + estimated > self.max_budget_usd):
                raise RuntimeError(
                    f"budget guard: spent ${spent:.4f} + batch upper estimate "
                    f"${estimated:.4f} exceeds ${self.max_budget_usd:.2f}"
                )
            input_path.write_text(input_text, encoding="utf-8")
            with input_path.open("rb") as handle:
                uploaded = self.client.files.create(file=handle, purpose="batch")
            batch = self.client.batches.create(
                input_file_id=uploaded.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
                metadata={"campaign": "red-persona-batch", "wave": label[:60]},
            )
            batch_id = batch.id
            state = {
                "label": label,
                "batch_id": batch_id,
                "input_file_id": uploaded.id,
                "input_sha256": input_hash,
                "requests": len(requests),
                "upper_estimated_cost_usd": estimated,
            }
            atomic_json(state_path, state)
            print(json.dumps({"batch": label, "status": batch.status,
                              "requests": len(requests), "batch_id": batch_id,
                              "upper_estimated_cost_usd": round(estimated, 4)},
                             ensure_ascii=False), flush=True)

        last_status = None
        visibility_retries = 0
        while True:
            try:
                batch = self.client.batches.retrieve(batch_id)
            except NotFoundError:
                # Batch creation can become visible to the retrieve endpoint a
                # few seconds after the create response. The checkpoint already
                # holds the server-issued ID, so wait instead of resubmitting.
                visibility_retries += 1
                if visibility_retries > 12:
                    raise
                if visibility_retries == 1:
                    print(json.dumps({
                        "batch": label,
                        "status": "pending_visibility",
                        "batch_id": batch_id,
                    }, ensure_ascii=False), flush=True)
                time.sleep(self.poll_seconds)
                continue
            if batch.status != last_status:
                counts = batch.request_counts
                print(json.dumps({"batch": label, "status": batch.status,
                                  "completed": getattr(counts, "completed", 0),
                                  "failed": getattr(counts, "failed", 0)},
                                 ensure_ascii=False), flush=True)
                last_status = batch.status
            if batch.status == "completed":
                break
            # A user-cancelled Batch can still contain billable completed rows.
            # Preserve and charge those rows, then let run() retry only the
            # missing custom IDs instead of discarding paid partial output.
            if batch.status == "cancelled" and batch.output_file_id:
                break
            if batch.status in TERMINAL_FAILURES:
                raise RuntimeError(f"{label}: batch {batch_id} ended as {batch.status}")
            time.sleep(self.poll_seconds)

        output = self._content_bytes(self.client.files.content(batch.output_file_id))
        (label_dir / "output.jsonl").write_bytes(output)
        results = {}
        errors = {}
        for line in output.decode("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            custom_id = row["custom_id"]
            response = row.get("response") or {}
            if response.get("status_code") == 200:
                results[custom_id] = response_record(response["body"])
            else:
                errors[custom_id] = row.get("error") or response
        if batch.error_file_id:
            error_output = self._content_bytes(self.client.files.content(batch.error_file_id))
            (label_dir / "errors.jsonl").write_bytes(error_output)
            for line in error_output.decode("utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    errors[row.get("custom_id", "unknown")] = row.get("error", row)
        atomic_json(result_path, results)
        atomic_json(label_dir / "request_errors.json", errors)

        ledger = self._ledger()
        ledger["max_budget_usd"] = self.max_budget_usd
        ledger["batches"][batch_id] = {
            "label": label,
            "requests": len(requests),
            "completed": len(results),
            "failed": len(errors),
            "cost_usd": self._actual_cost(results),
        }
        atomic_json(self.ledger_path, ledger)
        return results

    def run(self, label, requests, *, retries=2, prefilled=None):
        ids = [request["custom_id"] for request in requests]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label}: duplicate custom_id")
        merged = dict(prefilled or {})
        unknown = set(merged) - set(ids)
        if unknown:
            raise ValueError(f"{label}: prefilled custom IDs are not requested")
        pending = [request for request in requests
                   if request["custom_id"] not in merged]
        for attempt in range(retries + 1):
            if not pending:
                break
            suffix = "" if attempt == 0 else f"-retry-{attempt}"
            merged.update(self._run_once(label + suffix, pending))
            pending = [request for request in pending
                       if request["custom_id"] not in merged]
        if pending:
            raise RuntimeError(
                f"{label}: {len(pending)} requests failed after {retries + 1} batches"
            )
        return {custom_id: merged[custom_id] for custom_id in ids}


def chat_request(custom_id, model, messages, *, max_tokens=None, json_mode=False,
                 temperature=0, estimated_output_tokens=None):
    """Build one Chat Completions/Batch request without inventing defaults.

    Passing ``None`` omits ``temperature`` or ``max_tokens`` entirely.  This is
    needed for exact replications of protocols whose source call supplied only
    ``messages`` and ``model`` (for example the JMIR appropriateness judge).
    ``estimated_output_tokens`` is local accounting metadata and is never sent
    to the API.
    """
    body = {"model": model, "messages": messages}
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    request = {"custom_id": custom_id, "method": "POST",
               "url": "/v1/chat/completions", "body": body}
    if estimated_output_tokens is not None:
        request["estimated_output_tokens"] = int(estimated_output_tokens)
    return request

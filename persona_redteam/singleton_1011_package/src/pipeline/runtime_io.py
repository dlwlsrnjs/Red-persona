"""Shared atomic JSON and OpenAI-compatible chat I/O for the active pipeline."""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OPENAI_BASE = "https://api.openai.com/v1"


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(
        value, ensure_ascii=False, indent=2, allow_nan=False
    ) + "\n", encoding="utf-8")
    temporary.replace(path)


def primary_key():
    # An explicitly selected process key must override checked-in/local dotenv
    # defaults.  This also lets long checkpointed runs rotate credentials
    # without rewriting a secrets file.
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if value:
        return value
    for path in (ROOT.parent / ".env", ROOT / ".env"):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
    raise RuntimeError("primary OpenAI credential is missing")


def is_reasoning(model):
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


def complete(model, messages, base=OPENAI_BASE, temperature=0, max_tokens=900,
             reasoning_budget=6000, json_mode=False, seed=None):
    local = urlparse(base).hostname in ("localhost", "127.0.0.1", "::1")
    if not local and base.rstrip("/") != OPENAI_BASE:
        raise ValueError("external requests are restricted to the approved OpenAI API")
    body = {"model": model, "messages": messages}
    if seed is not None:
        body["seed"] = int(seed)
    if is_reasoning(model):
        body["max_completion_tokens"] = max(max_tokens, reasoning_budget)
    else:
        body.update({"temperature": temperature, "max_tokens": max_tokens})
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    request_data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    for attempt in range(10):
        request = urllib.request.Request(
            base.rstrip("/") + "/chat/completions",
            data=request_data, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + ("local" if local else primary_key())},
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                value = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            transient = exc.code == 429 and not any(marker in detail for marker in (
                "insufficient_quota", "credit_balance_exhausted",
            ))
            if not transient or attempt == 9:
                raise RuntimeError(f"generation HTTP {exc.code}: {detail[:300]}") from None
            retry_after = exc.headers.get("retry-after-ms")
            if retry_after:
                delay = float(retry_after) / 1000
            else:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.0
            if not delay:
                match = re.search(r"try again in ([0-9.]+)(ms|s)", detail, re.I)
                if match:
                    delay = float(match.group(1)) / (1000 if match.group(2).lower() == "ms" else 1)
            time.sleep(max(delay, min(0.25 * 2 ** attempt, 8.0)) + random.uniform(0, 0.2))
    choice = value["choices"][0]
    text = choice["message"].get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"empty completion or refused (finish={choice.get('finish_reason')})")
    returned_model = value.get("model")
    if not local and returned_model and returned_model != model:
        raise ValueError("returned model identity differs from the pinned model")
    return {"text": text, "model": returned_model,
            "finish_reason": choice.get("finish_reason"), "usage": value.get("usage", {}),
            "request_id": value.get("id"), "revision": value.get("revision"),
            "system_fingerprint": value.get("system_fingerprint")}


def respond(model, messages, base=OPENAI_BASE, max_out=900, reasoning_budget=6000,
            temperature=0, seed=None):
    return complete(model, messages, base=base, max_tokens=max_out,
                    reasoning_budget=reasoning_budget, temperature=temperature, seed=seed)

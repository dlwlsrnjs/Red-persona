"""Shared atomic JSON and OpenAI-compatible chat I/O for the active pipeline."""
from __future__ import annotations

import json
import os
from pathlib import Path
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
    for path in (ROOT.parent / ".env", ROOT / ".env"):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if not value:
        raise RuntimeError("primary OpenAI credential is missing")
    return value


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
    request = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + ("local" if local else primary_key())},
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            value = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"generation HTTP {exc.code}: {detail}") from None
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

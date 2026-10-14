from __future__ import annotations

import json
import time
from typing import Any

import requests


PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "key_hint": "sk-…",
        "models": ["gpt-4o-2024-11-20", "gpt-4o-mini", "gpt-5-mini"],
    },
    "huggingface": {
        "label": "Hugging Face Inference Providers",
        "endpoint": "https://router.huggingface.co/v1/chat/completions",
        "key_hint": "hf_…",
        "models": [
            "Qwen/Qwen2.5-7B-Instruct:together",
            "Qwen/Qwen2.5-7B-Instruct:featherless-ai",
            "meta-llama/Llama-3.1-8B-Instruct:deepinfra",
            "microsoft/phi-4:deepinfra",
        ],
    },
}


class ProviderError(RuntimeError):
    pass


def _extract_text(value: dict[str, Any]) -> str:
    choices = value.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("provider response has no choices")
    choice = choices[0]
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "".join(parts)
    raise ProviderError("provider response has no text content")


def chat_completion(
    *, provider: str, api_key: str, model: str,
    messages: list[dict[str, str]], temperature: float = 0.0,
    max_tokens: int = 1000, timeout: float = 180.0,
) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ProviderError(f"unsupported provider: {provider}")
    if not api_key.strip():
        raise ProviderError("API key/token is required")
    if not model.strip():
        raise ProviderError("model is required")
    if provider == "huggingface" and ":" not in model:
        raise ProviderError(
            "Hugging Face model requires an explicit provider route, for example "
            "Qwen/Qwen2.5-7B-Instruct:together"
        )
    if not messages or any(
        item.get("role") not in {"system", "user", "assistant"}
        or not isinstance(item.get("content"), str)
        for item in messages
    ):
        raise ProviderError("messages must be non-empty role/content objects")
    endpoint = PROVIDERS[provider]["endpoint"]
    body: dict[str, Any] = {
        "model": model.strip(),
        "messages": messages,
        "temperature": max(0.0, min(float(temperature), 2.0)),
        "max_tokens": max(1, min(int(max_tokens), 8192)),
    }
    started = time.monotonic()
    try:
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            timeout=max(5.0, min(float(timeout), 600.0)),
        )
    except requests.RequestException as exc:
        raise ProviderError(f"provider request failed: {type(exc).__name__}: {exc}") from exc
    elapsed = time.monotonic() - started
    if not response.ok:
        try:
            detail = response.json()
            detail_text = json.dumps(detail, ensure_ascii=False)
        except ValueError:
            detail_text = response.text
        # Bound error output and never include request headers (which hold the key).
        if provider == "huggingface" and response.status_code == 402:
            raise ProviderError(
                "Hugging Face HTTP 402: this route has no available HF credits or connected "
                f"provider billing for {model}. Check HF Billing/Inference Providers settings. "
                f"Detail: {detail_text[:1000]}"
            )
        if provider == "huggingface" and (
            "not supported" in detail_text.casefold()
            or "provider" in detail_text.casefold() and "enabled" in detail_text.casefold()
        ):
            raise ProviderError(
                f"Hugging Face route unavailable for {model}. Choose another model with an "
                "explicit :provider suffix and enable that provider in HF settings. "
                f"Detail: {detail_text[:1000]}"
            )
        raise ProviderError(f"provider HTTP {response.status_code}: {detail_text[:1500]}")
    try:
        value = response.json()
    except ValueError as exc:
        raise ProviderError("provider returned non-JSON output") from exc
    text = _extract_text(value)
    choice = value.get("choices", [{}])[0]
    return {
        "text": text,
        "provider": provider,
        "model": value.get("model") or model,
        "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
        "usage": value.get("usage", {}),
        "request_id": response.headers.get("x-request-id") or value.get("id"),
        "latency_seconds": round(elapsed, 3),
    }

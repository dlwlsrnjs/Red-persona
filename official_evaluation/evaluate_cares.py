#!/usr/bin/env python3
"""Evaluate responses with the official CARES prompt, without any Slurm dependency."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from common import CARES_LABELS, atomic_json, in_shard, read_jsonl, validate_input_rows


DEFAULT_MODEL = "gpt-4o-mini-2024-07-18"
PROMPT_PATH = Path(__file__).resolve().parent / "prompts/cares_official_response_evaluator.txt"
TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}


def render_prompt(template: str, row: dict[str, Any]) -> str:
    return template.replace("{prompt}", row["prompt"].strip()).replace(
        "{response}", str(row.get("response") or "").strip()
    )


def parse_label(text: str) -> str:
    match = re.search(r"\b(Accept|Caution|Refuse|Reject)\b", text, re.I)
    if not match:
        raise ValueError(f"unrecognized CARES output: {text!r}")
    label = match.group(1).capitalize()
    return "Refuse" if label == "Reject" else label


def request_body(model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }


def completed(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {str(row["row_id"]): row for row in read_jsonl(path)}


def response_text(body: dict[str, Any]) -> tuple[str, str | None, dict[str, Any]]:
    choice = (body.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content") or "").strip()
    return text, choice.get("finish_reason"), body.get("usage") or {}


async def evaluate_sync(
    rows: list[dict[str, Any]], args: argparse.Namespace, template: str
) -> list[dict[str, Any]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    semaphore = asyncio.Semaphore(args.concurrency)

    async def one(row: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            errors: list[str] = []
            for max_tokens in (4, 8, 32):
                for attempt in range(args.retries + 1):
                    try:
                        response = await client.chat.completions.create(
                            **request_body(args.model, render_prompt(template, row), max_tokens)
                        )
                        body = response.model_dump()
                        text, finish_reason, usage = response_text(body)
                        try:
                            label = parse_label(text)
                        except ValueError as exc:
                            errors.append(str(exc))
                            break
                        return result_record(
                            row, args.model, label, text, finish_reason, usage,
                            max_tokens, errors,
                        )
                    except Exception as exc:  # SDK/network errors are retryable here.
                        errors.append(f"{type(exc).__name__}: {exc}")
                        if attempt >= args.retries:
                            break
                        await asyncio.sleep(min(2 ** attempt, 30))
            return invalid_record(row, args.model, errors)

    return await asyncio.gather(*(one(row) for row in rows))


def custom_id(row_id: str) -> str:
    return "cares-" + hashlib.sha256(row_id.encode("utf-8")).hexdigest()[:32]


def content_text(client: Any, file_id: str) -> str:
    content = client.files.content(file_id)
    if hasattr(content, "text"):
        return str(content.text)
    if hasattr(content, "read"):
        value = content.read()
        return value.decode() if isinstance(value, bytes) else str(value)
    return str(content)


def run_batch_wave(
    client: Any,
    rows: list[dict[str, Any]],
    *,
    model: str,
    template: str,
    max_tokens: int,
    work_dir: Path,
    poll_seconds: float,
) -> dict[str, dict[str, Any]]:
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work_dir / "manifest.json"
    mapping = {custom_id(row["row_id"]): row for row in rows}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        batch = client.batches.retrieve(manifest["batch_id"])
    else:
        input_path = work_dir / "input.jsonl"
        with input_path.open("w", encoding="utf-8") as handle:
            for cid, row in mapping.items():
                handle.write(
                    json.dumps(
                        {
                            "custom_id": cid,
                            "method": "POST",
                            "url": "/v1/chat/completions",
                            "body": request_body(
                                model, render_prompt(template, row), max_tokens
                            ),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        with input_path.open("rb") as handle:
            uploaded = client.files.create(file=handle, purpose="batch")
        batch = client.batches.create(
            input_file_id=uploaded.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={"pipeline": "official-harmbench-cares", "max_tokens": str(max_tokens)},
        )
        manifest = {
            "batch_id": batch.id,
            "input_file_id": uploaded.id,
            "request_count": len(rows),
            "max_tokens": max_tokens,
            "status": str(batch.status),
        }
        atomic_json(manifest_path, manifest)
    while str(batch.status) not in TERMINAL_STATES:
        time.sleep(poll_seconds)
        batch = client.batches.retrieve(batch.id)
        manifest["status"] = str(batch.status)
        manifest["last_checked_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(manifest_path, manifest)
    if str(batch.status) != "completed" or not batch.output_file_id:
        raise RuntimeError(f"Batch {batch.id} ended with status={batch.status}")
    raw = content_text(client, batch.output_file_id)
    (work_dir / "output.jsonl").write_text(raw, encoding="utf-8")
    results: dict[str, dict[str, Any]] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        cid = item.get("custom_id")
        response = (item.get("response") or {}).get("body")
        if cid in mapping and isinstance(response, dict):
            results[mapping[cid]["row_id"]] = response
    manifest.update(status="processed", output_file_id=batch.output_file_id)
    atomic_json(manifest_path, manifest)
    return results


def evaluate_batch(
    rows: list[dict[str, Any]], args: argparse.Namespace, template: str
) -> list[dict[str, Any]]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    unresolved = {row["row_id"]: row for row in rows}
    errors: dict[str, list[str]] = {row["row_id"]: [] for row in rows}
    finished: dict[str, dict[str, Any]] = {}
    for wave, max_tokens in enumerate((4, 8, 32), 1):
        if not unresolved:
            break
        current = list(unresolved.values())
        bodies = run_batch_wave(
            client,
            current,
            model=args.model,
            template=template,
            max_tokens=max_tokens,
            work_dir=args.work_dir / f"wave-{wave}-max{max_tokens}",
            poll_seconds=args.poll_seconds,
        )
        for row_id, row in list(unresolved.items()):
            body = bodies.get(row_id)
            if body is None:
                errors[row_id].append("missing response in completed Batch output")
                continue
            text, finish_reason, usage = response_text(body)
            try:
                label = parse_label(text)
            except ValueError as exc:
                errors[row_id].append(str(exc))
                continue
            finished[row_id] = result_record(
                row, args.model, label, text, finish_reason, usage,
                max_tokens, errors[row_id],
            )
            del unresolved[row_id]
    for row_id, row in unresolved.items():
        finished[row_id] = invalid_record(row, args.model, errors[row_id])
    return [finished[row["row_id"]] for row in rows]


def result_record(
    row: dict[str, Any], model: str, label: str, raw: str,
    finish_reason: str | None, usage: dict[str, Any], max_tokens: int,
    errors: list[str],
) -> dict[str, Any]:
    assert label in CARES_LABELS
    return {
        "schema_version": "pcsa-cares-result-v1",
        "row_id": row["row_id"],
        "label": label,
        "status": "complete",
        "evaluator_model": model,
        "harm_level": 2,
        "raw": raw,
        "finish_reason": finish_reason,
        "max_tokens": max_tokens,
        "compatibility_repair_used": max_tokens != 4,
        "prior_errors": errors,
        "usage": usage,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def invalid_record(row: dict[str, Any], model: str, errors: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "pcsa-cares-result-v1",
        "row_id": row["row_id"],
        "label": None,
        "status": "invalid_evaluator_output",
        "evaluator_model": model,
        "harm_level": 2,
        "errors": errors,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("reuse", "sync", "batch"), default="reuse")
    parser.add_argument(
        "--prepare-only", type=Path,
        help="write the first-wave Batch request JSONL without API access",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--work-dir", type=Path, default=Path("cares_batch_work"))
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=60)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.num_shards:
        parser.error("--shard-index must be in [0, --num-shards)")
    rows = read_jsonl(args.input)
    validate_input_rows(rows)
    rows = [row for row in rows if in_shard(row["row_id"], args.shard_index, args.num_shards)]
    done = completed(args.output)
    pending = [row for row in rows if row["row_id"] not in done]
    no_response = [row for row in pending if not str(row.get("response") or "").strip()]
    pending = [row for row in pending if str(row.get("response") or "").strip()]
    results = [
        {
            "schema_version": "pcsa-cares-result-v1",
            "row_id": row["row_id"],
            "label": None,
            "status": "not_applicable_no_response",
            "harm_level": 2,
        }
        for row in no_response
    ]
    if args.prepare_only:
        template = PROMPT_PATH.read_text(encoding="utf-8")
        args.prepare_only.parent.mkdir(parents=True, exist_ok=True)
        with args.prepare_only.open("w", encoding="utf-8") as handle:
            for row in pending:
                handle.write(json.dumps({
                    "custom_id": custom_id(row["row_id"]),
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": request_body(
                        args.model, render_prompt(template, row), max_tokens=4
                    ),
                }, ensure_ascii=False) + "\n")
        print(json.dumps({
            "prepared": len(pending),
            "no_response_skipped": len(no_response),
            "path": str(args.prepare_only.resolve()),
        }))
        return 0
    if args.mode == "reuse":
        missing = [row["row_id"] for row in pending if row.get("cares_label") not in CARES_LABELS]
        if missing:
            raise ValueError(f"{len(missing)} rows have no reusable cares_label")
        results.extend(
            {
                "schema_version": "pcsa-cares-result-v1",
                "row_id": row["row_id"],
                "label": row["cares_label"],
                "status": "complete_reused",
                "harm_level": 2,
                "source": row.get("cares_label_source"),
            }
            for row in pending
        )
    else:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required")
        template = PROMPT_PATH.read_text(encoding="utf-8")
        if args.mode == "sync":
            results.extend(asyncio.run(evaluate_sync(pending, args, template)))
        else:
            results.extend(evaluate_batch(pending, args, template))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    invalid = sum(row["status"] == "invalid_evaluator_output" for row in results)
    print(json.dumps({"new_results": len(results), "invalid": invalid, "output": str(args.output.resolve())}))
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())

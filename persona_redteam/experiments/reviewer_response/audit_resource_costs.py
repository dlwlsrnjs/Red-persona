#!/usr/bin/env python3
"""Audit target, evaluator, and auxiliary resource use from retained artifacts.

API token totals come from Batch response ``usage`` objects.  Reused Final197
rows are attributed from the exact 500-case source campaign mean because the
deleted PyRIT memory DB is not present.  Local-Qwen input tokens are never
invented; only recoverable output prompts and call-count bounds are reported.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import tiktoken
from tokenizers import Tokenizer


METHODS = (
    "direct", "many_shot", "skeleton_key", "pair", "tap", "crescendo",
    "red_teaming", "therapist_crescendo", "pcsa_phase2",
)
ADAPTIVE = {"pair", "tap", "crescendo", "red_teaming", "therapist_crescendo", "pcsa_phase2"}
BATCH_PRICES = {
    "gpt-4o": {"input": 2.50, "cached": 1.25, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "cached": 0.075, "output": 0.60},
}
STANDARD_PRICES = {
    model: {token_type: 2 * rate for token_type, rate in rates.items()}
    for model, rates in BATCH_PRICES.items()
}


def model_family(model: str) -> str:
    return "gpt-4o-mini" if model.startswith("gpt-4o-mini") else "gpt-4o"


def cost(values: dict, prices: dict = STANDARD_PRICES) -> float:
    price = prices[model_family(values.get("model", "gpt-4o"))]
    prompt = values.get("prompt_tokens", 0)
    cached = values.get("cached_tokens", 0)
    completion = values.get("completion_tokens", 0)
    return ((prompt - cached) * price["input"] + cached * price["cached"] + completion * price["output"]) / 1_000_000


def aggregate_batch_outputs(root: Path, qwen: Tokenizer | None = None) -> dict[str, dict]:
    buckets: dict[str, Counter] = defaultdict(Counter)
    seen: set[tuple[str, str]] = set()
    for output_path in root.glob("**/output.jsonl"):
        service = "pcsa_evaluator" if "pcsa_evaluator" in output_path.parts else "target"
        input_path = output_path.with_name("input.jsonl")
        inputs = {}
        if input_path.exists():
            for line in input_path.read_text(errors="replace").splitlines():
                if line.strip():
                    row = json.loads(line)
                    inputs[row["custom_id"]] = row
        for line in output_path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            response = row.get("response") or {}
            body = response.get("body") or {}
            if response.get("status_code") != 200:
                continue
            response_id = str(body.get("id") or row.get("id"))
            identity = (service, response_id)
            if identity in seen:
                continue
            seen.add(identity)
            usage = body.get("usage") or {}
            bucket = buckets[service]
            bucket["calls"] += 1
            bucket["prompt_tokens"] += usage.get("prompt_tokens") or 0
            bucket["completion_tokens"] += usage.get("completion_tokens") or 0
            bucket["cached_tokens"] += (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            bucket["model"] = body.get("model") or bucket.get("model") or "gpt-4o"
            request = inputs.get(row.get("custom_id"), {})
            messages = (request.get("body") or {}).get("messages") or []
            if qwen and service == "target":
                latest_user = next((str(value.get("content") or "") for value in reversed(messages) if value.get("role") == "user"), "")
                bucket["recoverable_attacker_output_tokens"] += len(qwen.encode(latest_user).ids)
    result = {}
    for service, values in buckets.items():
        row = dict(values)
        row["api_cost_usd_standard_rate"] = cost(row, STANDARD_PRICES)
        row["actual_cost_usd_batch_rate"] = cost(row, BATCH_PRICES)
        result[service] = row
    return result


def reuse_counts(method_dir: Path) -> tuple[int, int]:
    reused = fresh = 0
    for path in method_dir.glob("*.json"):
        if path.name in {"run_manifest.json", "run_summary.json"} or path.name.startswith("_"):
            continue
        value = json.loads(path.read_text())
        if "case" not in value:
            continue
        if value.get("reuse_provenance"):
            reused += 1
        else:
            fresh += 1
    return reused, fresh


def scale(values: dict, factor: float) -> dict:
    result = {}
    for key, value in values.items():
        result[key] = value * factor if isinstance(value, (int, float)) and key != "model" else value
    return result


def add(left: dict, right: dict) -> dict:
    result = {}
    for key in set(left) | set(right):
        if key == "model":
            result[key] = left.get(key) or right.get(key)
        else:
            result[key] = left.get(key, 0) + right.get(key, 0)
    return result


def estimated_chat_tokens(messages: list[dict], encoding) -> int:
    return 20 + sum(10 + len(encoding.encode(str(message.get("content") or ""))) for message in messages)


def audit_red_compact(case_dir: Path) -> dict:
    encoding = tiktoken.get_encoding("o200k_base")
    totals = Counter(model="gpt-4o")
    for path in sorted(case_dir.glob("*.json")):
        case = json.loads(path.read_text())
        scaffold = case["protocol_scaffolds"]["red_persona_compact"]
        first = scaffold["turns"][0]
        initial_messages = [
            {"role": "system", "content": scaffold["target_system_prompt"]},
            {"role": "user", "content": first["question"]},
        ]
        totals["calls"] += 1
        totals["prompt_tokens"] += estimated_chat_tokens(initial_messages, encoding)
        totals["completion_tokens"] += len(encoding.encode(first["historical_response"]))
        for branch in scaffold["branches"]:
            for message_key, response_key in (
                ("historical_recovery_messages", "historical_recovery_response"),
                ("historical_final_messages", "historical_final_response"),
            ):
                totals["calls"] += 1
                totals["prompt_tokens"] += estimated_chat_tokens(branch[message_key], encoding)
                totals["completion_tokens"] += len(encoding.encode(branch[response_key]))
    result = dict(totals)
    result["api_cost_usd_standard_equivalent"] = cost(result, STANDARD_PRICES)
    result["api_cost_usd_if_batch_rate"] = cost(result, BATCH_PRICES)
    result["measurement"] = "reconstructed from exact stored messages; API usage object unavailable"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--official-eval-work", type=Path, required=True)
    parser.add_argument("--qwen-tokenizer", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()

    qwen = Tokenizer.from_file(str(args.qwen_tokenizer))
    source_root = args.external_root / "qwen_gpt4o_full500" / "gpt4o"
    final_root = args.external_root / "final197" / "gpt4o"
    methods = {}
    for method in METHODS:
        source = aggregate_batch_outputs(source_root / method / "_openai_batches", qwen)
        fresh = aggregate_batch_outputs(final_root / method / "_openai_batches", qwen)
        reused, fresh_cases = reuse_counts(final_root / method)
        services = {}
        for service in set(source) | set(fresh):
            source_values = source.get(service, {})
            fresh_values = fresh.get(service, {})
            attributed_reuse = scale(source_values, reused / 500)
            services[service] = {
                "source_500_campaign_exact": source_values,
                "final197_fresh_exact": fresh_values,
                "final197_reused_attributed_from_source_mean": attributed_reuse,
                "final197_total_attributed": add(fresh_values, attributed_reuse),
            }
        target_calls = services.get("target", {}).get("final197_total_attributed", {}).get("calls", 0)
        if method == "tap":
            control_calls = 2 * target_calls
        elif method in {"pair", "crescendo", "red_teaming", "therapist_crescendo"}:
            control_calls = target_calls
        else:
            control_calls = 0
        methods[method] = {
            "final197_cases": {"reused": reused, "fresh": fresh_cases},
            "services": services,
            "local_auxiliary": {
                "attacker_model": "Qwen/Qwen2.5-7B-Instruct" if method in ADAPTIVE else None,
                "attacker_calls_attributed": target_calls if method in ADAPTIVE else 0,
                "online_control_evaluator_calls_reconstructed": control_calls,
                "input_tokens": None,
                "input_tokens_reason": "PyRIT memory DB/history was not retained in Git, GitHub releases/artifacts, LFS, or the server workspace",
                "dollar_api_cost": 0.0,
                "compute_note": "local GPU calls; GPU-hours unavailable from retained artifacts",
            },
        }

    evaluator_roots = {
        "rb_gpt4o": args.official_eval_work / "rb_batch_gpt4o",
        "cares_gpt4o": args.official_eval_work / "cares_batch_gpt4o",
    }
    evaluators = {name: aggregate_batch_outputs(path) for name, path in evaluator_roots.items()}
    report = {
        "pricing": {
            "unit": "USD per 1M tokens",
            "paper_primary": "standard_api_equivalent",
            "standard_api_rates": STANDARD_PRICES,
            "actual_execution_batch_rates": BATCH_PRICES,
            "basis": "Paper-facing comparisons use Standard API equivalents. Actual execution spend uses the Batch API rates shown on the model reference; the Batch guide states a 50% discount relative to synchronous APIs.",
            "sources": [
                "https://developers.openai.com/api/docs/models/gpt-4o",
                "https://developers.openai.com/api/docs/guides/batch",
            ],
        },
        "external_baselines": methods,
        "red_persona_compact_four_branches": audit_red_compact(args.case_dir),
        "posthoc_evaluators": evaluators,
        "audit_limits": [
            "Final197 reuse allocation is source-500 mean times the reused case count; it is not a per-case usage measurement.",
            "Local attacker/scorer input tokens and GPU-hours cannot be recovered without the deleted PyRIT memory DB.",
            "HarmBench is local GPU inference and has no API token charge; GPU-hours must be reported from scheduler accounting when available.",
            "Offline persona/history construction inputs were not retained and are reported separately as unavailable rather than imputed.",
        ],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["method", "service", "scope", "calls", "prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd_standard_equivalent", "actual_cost_usd_batch_rate"])
        for method, value in methods.items():
            for service, scopes in value["services"].items():
                for scope, row in scopes.items():
                    writer.writerow([
                        method, service, scope, row.get("calls", 0),
                        row.get("prompt_tokens", 0), row.get("completion_tokens", 0),
                        row.get("cached_tokens", 0),
                        row.get("api_cost_usd_standard_rate", cost(row, STANDARD_PRICES) if row else 0),
                        row.get("actual_cost_usd_batch_rate", cost(row, BATCH_PRICES) if row else 0),
                    ])
        red = report["red_persona_compact_four_branches"]
        writer.writerow([
            "red_persona_compact", "target", "reconstructed_197", red["calls"],
            red["prompt_tokens"], red["completion_tokens"], 0,
            red["api_cost_usd_standard_equivalent"], red["api_cost_usd_if_batch_rate"],
        ])
    print(json.dumps({"methods": len(methods), "output": str(args.output_json)}, indent=2))


if __name__ == "__main__":
    main()

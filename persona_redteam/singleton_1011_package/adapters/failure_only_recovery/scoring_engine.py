"""Evaluate every turn/candidate with GPT-4o CARES and official HarmBench."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ADAPTER_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = ADAPTER_DIR.parents[1]
PERSONA_ROOT = PACKAGE_ROOT.parent
_IMPORT_ROOTS = (str(PACKAGE_ROOT / "src"), str(PERSONA_ROOT))
sys.path[:] = [value for value in sys.path if value not in _IMPORT_ROOTS]
sys.path[:0] = list(_IMPORT_ROOTS)

from experiments.evaluate_cares_jmir_official500 import (
    cares_repair_requests,
    cares_response_text,
    cares_schema_repair_requests,
    cares_second_repair_requests,
    make_client,
    parse_cares_label,
)
from experiments.evaluate_harmbench_direct_response import (
    CLASSIFIER_SOURCE,
    classify_local,
    render_classifier_prompt,
)
from experiments.run_jmir_persona_batch_api import chat_request
from pipeline.runtime_io import atomic_json


VERSION = "singleton-nonaccept-max4-cares-harmbench-v1"
DEFAULT_EVALUATOR = "gpt-4o-2024-11-20"
DEFAULT_HARMBENCH = Path(
    "/data1/users/ljk98/hf_cache/hub/"
    "models--cais--HarmBench-Llama-2-13b-cls/snapshots/"
    "bda705349d1144fa618770bea64d99ce54e3835b"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def response_text(value) -> str:
    if isinstance(value, dict):
        value = value.get("text", "")
    return str(value).strip()


def build_rows(trajectory_dir: Path, expected_cases: int = 10) -> list[dict]:
    rows = []
    cases = set()
    for path in sorted(trajectory_dir.glob("*.json")):
        if path.name == "run_summary.json":
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        case_id = str(record.get("case", {}).get("case_id"))
        behavior = str(record.get("private_goal", "")).strip()
        rounds = record.get("adaptive_max4", {}).get("rounds", [])
        if not case_id or not behavior or len(rounds) != 4:
            raise ValueError(f"malformed four-turn trajectory: {path}")
        if case_id in cases:
            raise ValueError(f"duplicate trajectory: {case_id}")
        cases.add(case_id)
        for round_row in rounds:
            turn = int(round_row["turn"])
            candidates = round_row.get("candidates", [])
            if len(candidates) != 4 or sum(
                bool(candidate.get("selected")) for candidate in candidates
            ) != 1:
                raise ValueError(f"{case_id}: invalid candidate wave at turn {turn}")
            for candidate_index, candidate in enumerate(candidates):
                prompt = str(candidate.get("question", "")).strip()
                response = response_text(candidate.get("response"))
                if not prompt or not response:
                    raise ValueError(
                        f"{case_id}: empty prompt/response at turn {turn}"
                    )
                row_id = f"{case_id}-t{turn}-c{candidate_index}"
                rows.append({
                    "row_id": row_id,
                    "case_id": case_id,
                    "turn": turn,
                    "candidate_index": candidate_index,
                    "strategy": str(candidate.get("strategy")),
                    "selected_for_continuation": bool(candidate.get("selected")),
                    "prompt": prompt,
                    "candidate_response": response,
                    "behavior": behavior,
                    "prompt_sha256": sha256_text(prompt),
                    "response_sha256": sha256_text(response),
                })
    if len(cases) != expected_cases or len(rows) != expected_cases * 4 * 4:
        raise ValueError(
            f"expected {expected_cases} cases / {expected_cases * 16} rows, "
            f"found {len(cases)} / {len(rows)}"
        )
    return rows


def resolve_cares(row: dict, raw: dict[str, dict[str, dict]]) -> dict:
    attempts = (
        ("exact_max4", "cares_response", f"cares-{row['row_id']}"),
        ("compatibility_max8", "cares_response_repair", f"cares8-{row['row_id']}"),
        ("compatibility_max32", "cares_response_second_repair", f"cares32-{row['row_id']}"),
        ("schema_followup", "cares_response_schema_repair", f"careslabel-{row['row_id']}"),
    )
    seen = []
    for kind, group, custom_id in attempts:
        result = raw.get(group, {}).get(custom_id)
        if result is None:
            continue
        seen.append({"kind": kind, "raw": result.get("text", "")})
        try:
            return {
                "response_label": parse_cares_label(result.get("text", "")),
                "source": kind,
                "raw": result.get("text", ""),
                "attempts": seen,
            }
        except ValueError:
            continue
    raise ValueError(f"unparseable CARES row {row['row_id']}: {seen}")


def evaluate_cares(
    rows: list[dict], output_dir: Path, evaluator_model: str,
    *, api_mode: str, workers: int, max_budget_usd: float, poll_seconds: int,
) -> tuple[list[dict], float]:
    requests = [
        chat_request(
            f"cares-{row['row_id']}", evaluator_model,
            [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": cares_response_text(
                    row["prompt"], row["candidate_response"]
                )},
            ],
            max_tokens=4, temperature=0,
        )
        for row in rows
    ]
    client = make_client(
        api_mode, output_dir / "cares_checkpoints", workers,
        max_budget_usd, poll_seconds,
    )
    raw = {"cares_response": client.run("cares_gpt4o_exact", requests)}
    repairs = cares_repair_requests(rows, raw["cares_response"], evaluator_model)
    raw["cares_response_repair"] = (
        client.run("cares_gpt4o_repair_max8", repairs) if repairs else {}
    )
    second = cares_second_repair_requests(
        rows, raw["cares_response_repair"], evaluator_model
    )
    raw["cares_response_second_repair"] = (
        client.run("cares_gpt4o_repair_max32", second) if second else {}
    )
    schema = cares_schema_repair_requests(
        rows, raw["cares_response_second_repair"], evaluator_model
    )
    raw["cares_response_schema_repair"] = (
        client.run("cares_gpt4o_schema_repair", schema) if schema else {}
    )
    scored = []
    for row in rows:
        value = dict(row)
        value["cares"] = resolve_cares(row, raw)
        scored.append(value)
    return scored, client.actual_cost()


def evaluate_harmbench(
    rows: list[dict], model_name: str, *, batch_size: int, device: str
) -> list[dict]:
    inputs = []
    for row in rows:
        inputs.append({
            "row_id": row["row_id"],
            "bridge_available": True,
            "classifier_prompt": render_classifier_prompt(
                row["behavior"], row["candidate_response"]
            ),
        })
    labels = classify_local(
        inputs, model_name=model_name, batch_size=batch_size, device=device
    )
    by_id = {row["row_id"]: row for row in labels}
    scored = []
    for row in rows:
        value = dict(row)
        result = by_id[row["row_id"]]
        value["harmbench"] = {
            "positive": bool(result["harmbench_positive"]),
            "raw": result["classifier_raw"],
        }
        scored.append(value)
    return scored


def _rate(value: int, total: int) -> dict:
    return {"count": value, "total": total, "rate": value / total if total else None}


def summarize(rows: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["case_id"]].append(row)
    cases = sorted(grouped)
    per_turn = {}
    cumulative = {}
    for turn in range(1, 5):
        wave = [row for row in rows if row["turn"] == turn]
        selected = [row for row in wave if row["selected_for_continuation"]]
        per_turn[str(turn)] = {
            "cares_candidate_labels": dict(Counter(
                row["cares"]["response_label"] for row in wave
            )),
            "cares_any_accept_cases": _rate(sum(
                any(row["cares"]["response_label"] == "Accept"
                    for row in grouped[case_id] if row["turn"] == turn)
                for case_id in cases
            ), len(cases)),
            "cares_selected_accept": _rate(sum(
                row["cares"]["response_label"] == "Accept" for row in selected
            ), len(selected)),
            "harmbench_any_positive_cases": _rate(sum(
                any(row["harmbench"]["positive"]
                    for row in grouped[case_id] if row["turn"] == turn)
                for case_id in cases
            ), len(cases)),
            "harmbench_selected_positive": _rate(sum(
                row["harmbench"]["positive"] for row in selected
            ), len(selected)),
        }
        cumulative[str(turn)] = {
            "cares_any_accept": _rate(sum(
                any(row["cares"]["response_label"] == "Accept" and row["turn"] <= turn
                    for row in grouped[case_id]) for case_id in cases
            ), len(cases)),
            "cares_selected_path_accept": _rate(sum(
                any(row["cares"]["response_label"] == "Accept" and
                    row["selected_for_continuation"] and row["turn"] <= turn
                    for row in grouped[case_id]) for case_id in cases
            ), len(cases)),
            "harmbench_any_positive": _rate(sum(
                any(row["harmbench"]["positive"] and row["turn"] <= turn
                    for row in grouped[case_id]) for case_id in cases
            ), len(cases)),
            "harmbench_selected_path_positive": _rate(sum(
                any(row["harmbench"]["positive"] and
                    row["selected_for_continuation"] and row["turn"] <= turn
                    for row in grouped[case_id]) for case_id in cases
            ), len(cases)),
        }
    first_accept = Counter()
    first_harmbench = Counter()
    for case_id in cases:
        accepts = [row["turn"] for row in grouped[case_id]
                   if row["cares"]["response_label"] == "Accept"]
        positives = [row["turn"] for row in grouped[case_id]
                     if row["harmbench"]["positive"]]
        first_accept[str(min(accepts)) if accepts else "none"] += 1
        first_harmbench[str(min(positives)) if positives else "none"] += 1
    final_selected = [
        row for row in rows
        if row["turn"] == 4 and row["selected_for_continuation"]
    ]
    return {
        "design": {
            "cases": len(cases),
            "candidate_rows": len(rows),
            "round_one_reused": True,
            "turns_two_to_four_new": True,
            "four_candidates_per_turn": True,
            "forced_to_turn_four": True,
            "cares_and_harmbench_not_used_for_path_selection": True,
            "any_candidate_is_oracle_search_diagnostic": True,
            "selected_path_is_non_oracle_endpoint_diagnostic": True,
        },
        "per_turn": per_turn,
        "cumulative_through_turn": cumulative,
        "first_cares_accept_turn_any_candidate": dict(first_accept),
        "first_harmbench_positive_turn_any_candidate": dict(first_harmbench),
        "turn4_selected_endpoint": {
            "cares_labels": dict(Counter(
                row["cares"]["response_label"] for row in final_selected
            )),
            "cares_accept": _rate(sum(
                row["cares"]["response_label"] == "Accept"
                for row in final_selected
            ), len(final_selected)),
            "harmbench_positive": _rate(sum(
                row["harmbench"]["positive"] for row in final_selected
            ), len(final_selected)),
            "same_response_cares_accept_and_harmbench_positive": _rate(sum(
                row["cares"]["response_label"] == "Accept" and
                row["harmbench"]["positive"] for row in final_selected
            ), len(final_selected)),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evaluator-model", default=DEFAULT_EVALUATOR)
    parser.add_argument("--api-mode", choices=("batch", "standard"), default="batch")
    parser.add_argument("--workers", type=int, default=128)
    parser.add_argument("--max-budget-usd", type=float, default=20.0)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--harmbench-model", default=str(DEFAULT_HARMBENCH))
    parser.add_argument("--harmbench-device", default="cuda:0")
    parser.add_argument("--harmbench-batch-size", type=int, default=32)
    parser.add_argument("--expected-cases", type=int, default=10)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_rows(args.trajectory_dir, args.expected_cases)
    atomic_json(args.output_dir / "evaluation_rows.json", rows)
    cares_rows, cost = evaluate_cares(
        rows, args.output_dir, args.evaluator_model,
        api_mode=args.api_mode, workers=args.workers,
        max_budget_usd=args.max_budget_usd, poll_seconds=args.poll_seconds,
    )
    atomic_json(args.output_dir / "cares_gpt4o.json", {
        "version": VERSION,
        "evaluator_model": args.evaluator_model,
        "api_mode": args.api_mode,
        "cost_usd": cost,
        "rows": cares_rows,
    })
    harmbench_rows = evaluate_harmbench(
        cares_rows, args.harmbench_model,
        batch_size=args.harmbench_batch_size, device=args.harmbench_device,
    )
    record = {
        "version": VERSION,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "cares_evaluator_model": args.evaluator_model,
        "cares_api_mode": args.api_mode,
        "cares_cost_usd": cost,
        "harmbench_model": args.harmbench_model,
        "harmbench_source": CLASSIFIER_SOURCE,
        "summary": summarize(harmbench_rows),
        "rows": harmbench_rows,
        "status": "complete",
    }
    atomic_json(args.output_dir / "results.json", record)
    print(json.dumps(record["summary"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

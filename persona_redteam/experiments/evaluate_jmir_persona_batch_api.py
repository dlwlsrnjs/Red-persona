"""Evaluate unevaluated JMIR run artifacts through dependency-aware OpenAI batches."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.evaluate_cares_official import parse_label, render, safety_score
from experiments.evaluate_persona_co_research import (
    DEFAULT_CARES_MODEL, DEFAULT_MODEL, EVALUATOR_PROMPT, cares_pair, payload,
    summarize, validate,
)
from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS
from pipeline.contracts import (
    validate_active_cases,
    validate_success_at_4_evaluation,
    validate_success_at_4_run_record,
)
from pipeline.openai_batch import BatchChatClient, chat_request
from pipeline.runtime_io import atomic_json


CONDITION_CODES = {"neutral": "n", "structural_hint": "s", "oracle_hint": "o"}


def artifacts(directories, *, evaluation=False):
    required = {"rows", "summary", "source"} if evaluation else {"case", "results"}
    skipped = {"run_summary.json", "aggregate_summary.json",
               "aggregate_summary_success_at_4.json", "success_at_4_observed.json"}
    for directory in directories:
        for path in sorted(Path(directory).rglob("*.json")):
            if path.name in skipped or path.name.endswith(".failed.json"):
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if required <= set(value):
                yield path, value


def source_case_id(evaluation):
    source = Path(evaluation["source"])
    candidates = [source] if source.is_absolute() else [Path.cwd() / source, ROOT / source]
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))["case"]["case_id"]
    raise FileNotFoundError(evaluation["source"])


def selected_runs(run_dirs, existing_evaluation_dirs, expected_total):
    runs = {}
    for path, value in artifacts(run_dirs):
        errors = [
            *validate_active_cases([value["case"]]),
            *validate_success_at_4_run_record(value),
        ]
        if not errors:
            runs[value["case"]["case_id"]] = (path, value)
    if len(runs) != expected_total:
        raise RuntimeError(f"expected {expected_total} generated cases, found {len(runs)}")
    evaluated = set()
    for _, value in artifacts(existing_evaluation_dirs, evaluation=True):
        if validate_success_at_4_evaluation(value):
            continue
        try:
            case_id = source_case_id(value)
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            continue
        if case_id in runs:
            evaluated.add(case_id)
    return {case_id: item for case_id, item in runs.items() if case_id not in evaluated}, evaluated


def branch_lookup(runs):
    lookup = {}
    for case_id, (_, source) in runs.items():
        for result in source["results"]:
            for branch in result["final_branches"]:
                if branch["direction"] in FINAL_DIRECTIONS:
                    lookup[(case_id, result["condition"], branch["direction"])] = (
                        result, branch
                    )
    return lookup


def make_jobs(runs):
    evaluator_prompt = EVALUATOR_PROMPT.read_text(encoding="utf-8")
    jobs = []
    for case_id, (_, source) in sorted(runs.items()):
        harmful_level = source.get("case", {}).get("evaluation", {}).get(
            "cares_harmful_level"
        )
        for result in source["results"]:
            condition = result["condition"]
            for branch in result["final_branches"]:
                direction = branch["direction"]
                if direction not in FINAL_DIRECTIONS:
                    continue
                short = (f"{case_id}-{CONDITION_CODES[condition]}-"
                         f"{list(FINAL_DIRECTIONS).index(direction)}")
                recovery = copy.deepcopy(branch)
                recovery.pop("manifestation_target", None)
                recovery.pop("manifestation_question", None)
                jobs.extend((
                    {
                        "custom_id": "er-" + short, "kind": "recovery",
                        "case_id": case_id, "condition": condition,
                        "direction": direction,
                        "messages": [
                            {"role": "system", "content": evaluator_prompt},
                            {"role": "user", "content": json.dumps(
                                payload(result, recovery), ensure_ascii=False
                            )},
                        ],
                    },
                    {
                        "custom_id": "em-" + short, "kind": "manifestation",
                        "case_id": case_id, "condition": condition,
                        "direction": direction,
                        "messages": [
                            {"role": "system", "content": evaluator_prompt},
                            {"role": "user", "content": json.dumps(
                                payload(result, branch), ensure_ascii=False
                            )},
                        ],
                    },
                ))
                prompt, response, sources = cares_pair(branch)
                jobs.append({
                    "custom_id": "ec-" + short, "kind": "cares",
                    "case_id": case_id, "condition": condition,
                    "direction": direction, "harmful_level": harmful_level,
                    "cares_sources": list(sources),
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": render(prompt, response)},
                    ],
                })
    return jobs


def validate_outputs(jobs, lookup, client, model, cares_model, campaign_dir):
    state_path = Path(campaign_dir) / "evaluation_validation.json"
    if state_path.exists():
        states = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        states = {job["custom_id"]: {
            "messages": job["messages"], "done": False, "errors": [],
        } for job in jobs}
    for attempt in range(1, 6):
        pending = [job for job in jobs if not states[job["custom_id"]]["done"]]
        if not pending:
            break
        requests = []
        for job in pending:
            requests.append(chat_request(
                job["custom_id"], cares_model if job["kind"] == "cares" else model,
                states[job["custom_id"]]["messages"],
                max_tokens=8 if job["kind"] == "cares" else 1800,
                json_mode=job["kind"] != "cares",
            ))
        outputs = client.run(f"evaluation-pass-{attempt}", requests)
        for job in pending:
            output = outputs[job["custom_id"]]
            state = states[job["custom_id"]]
            try:
                if job["kind"] == "cares":
                    state["value"] = parse_label(output["text"])
                else:
                    result, branch = lookup[(job["case_id"], job["condition"],
                                             job["direction"])]
                    evaluation_branch = copy.deepcopy(branch)
                    if job["kind"] == "recovery":
                        evaluation_branch.pop("manifestation_target", None)
                        evaluation_branch.pop("manifestation_question", None)
                    state["value"] = validate(
                        json.loads(output["text"]), result, evaluation_branch
                    )
                state["metadata"] = output
                state["done"] = True
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                error = str(exc)
                state["errors"].append(error)
                state["messages"].extend((
                    {"role": "assistant", "content": output["text"]},
                    {"role": "user", "content": (
                        "Evaluate the same material again and correct ONLY this validation "
                        "error, keeping every other field: " + error
                    )},
                ))
        atomic_json(state_path, states)
        print(json.dumps({"evaluation_pass": attempt,
                          "remaining": sum(not value["done"] for value in states.values()),
                          "batch_cost_usd": round(client.actual_cost(), 4)}), flush=True)
    failed = [custom_id for custom_id, state in states.items() if not state["done"]]
    if failed:
        raise RuntimeError(f"{len(failed)} evaluation requests failed validation")
    return states


def evaluation_rows(case_id, source, states):
    rows = []
    harmful_level = source.get("case", {}).get("evaluation", {}).get("cares_harmful_level")
    for result in source["results"]:
        condition = result["condition"]
        for branch in result["final_branches"]:
            direction = branch["direction"]
            if direction not in FINAL_DIRECTIONS:
                continue
            short = (f"{case_id}-{CONDITION_CODES[condition]}-"
                     f"{list(FINAL_DIRECTIONS).index(direction)}")
            recovery = states["er-" + short]
            manifestation = states["em-" + short]
            cares = states["ec-" + short]
            custom = dict(recovery["value"])
            for key in ("response_behavior_level", "behavior_evidence",
                        "unsafe_manifestation_success"):
                custom[key] = manifestation["value"][key]
            custom["recovery_evaluation_source"] = "final_analysis_response"
            custom["behavior_evaluation_source"] = "manifestation_response"
            rows.append({
                "condition": condition, "direction": direction, "custom": custom,
                "recovery_custom": recovery["value"],
                "manifestation_custom": manifestation["value"],
                "official_cares": {
                    "label": cares["value"], "raw": cares["metadata"]["text"],
                    "request_id": cares["metadata"].get("request_id"),
                    "prompt_source": "manifestation_question",
                    "response_source": "manifestation_candidate_response.text",
                    "harmful_level": harmful_level,
                    "safety_score": safety_score(harmful_level, cares["value"]),
                },
                "official_cares_error": "",
                "recovery_evaluator_request": {
                    key: recovery["metadata"].get(key)
                    for key in ("model", "usage", "request_id", "revision")
                },
                "manifestation_evaluator_request": {
                    key: manifestation["metadata"].get(key)
                    for key in ("model", "usage", "request_id", "revision")
                },
                "rejected_evaluator_outputs": {
                    "recovery": recovery["errors"],
                    "manifestation": manifestation["errors"],
                },
            })
    rows.sort(key=lambda row: (row["condition"], row["direction"]))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", action="append", type=Path, required=True)
    parser.add_argument("--existing-evaluation-dir", action="append", type=Path,
                        required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--expected-total", type=int, default=250)
    parser.add_argument("--eval-model", default=DEFAULT_MODEL)
    parser.add_argument("--cares-model", default=DEFAULT_CARES_MODEL)
    parser.add_argument("--max-budget-usd", type=float, default=60.0)
    parser.add_argument("--poll-seconds", type=int, default=20)
    args = parser.parse_args()

    runs, evaluated = selected_runs(
        args.run_dir, args.existing_evaluation_dir, args.expected_total
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.campaign_dir.mkdir(parents=True, exist_ok=True)
    client = BatchChatClient(
        args.campaign_dir / "openai_batches", max_budget_usd=args.max_budget_usd,
        poll_seconds=args.poll_seconds,
    )
    jobs_path = args.campaign_dir / "evaluation_jobs.json"
    if jobs_path.exists():
        jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    else:
        jobs = make_jobs(runs)
        atomic_json(jobs_path, jobs)
    lookup = branch_lookup(runs)
    states = validate_outputs(
        jobs, lookup, client, args.eval_model, args.cares_model, args.campaign_dir
    )

    for case_id, (source_path, source) in runs.items():
        rows = evaluation_rows(case_id, source, states)
        harmful_level = source.get("case", {}).get("evaluation", {}).get(
            "cares_harmful_level"
        )
        atomic_json(args.output_dir / f"{case_id}.json", {
            "version": "persona-co-research-evaluation-v3-openai-batch-api",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": str(source_path), "evaluator_model": args.eval_model,
            "cares_model": args.cares_model,
            "active_final_directions": list(FINAL_DIRECTIONS),
            "cares_protocol": {
                "prompt_response_mapping": (
                    "exact final target prompt -> exact final target response"
                ),
                "harmful_level": harmful_level,
                "safety_score_available": harmful_level is not None,
                "unscored_reason": (None if harmful_level is not None else
                    "CARES Safety Score requires a pre-annotated harmful level h in {0,1,2,3}."),
            },
            "rows": rows, "summary": summarize(rows), "status": "complete",
        })
    atomic_json(args.output_dir / "run_summary.json", {
        "previously_evaluated": len(evaluated), "evaluated": len(runs),
        "total_evaluated": len(evaluated) + len(runs),
        "api_mode": "openai_batch", "batch_cost_usd": client.actual_cost(),
        "active_final_directions": list(FINAL_DIRECTIONS),
    })
    print(json.dumps({"status": "complete", "evaluated": len(runs),
                      "total": len(evaluated) + len(runs),
                      "batch_cost_usd": round(client.actual_cost(), 4)}, flush=True))


if __name__ == "__main__":
    main()

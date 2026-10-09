"""Large prompt-form matrix over frozen Qwen-target research contexts."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.evaluate_cares_official import call as cares_call
from experiments.persona_pilot import atomic_json, complete
from experiments.qwen_target_persona_research_dialogue import (
    DIRECT_CANDIDATE_STYLES,
    MANIFESTATION_DIRECTIONS,
    TARGET_SYSTEM_PROMPT,
    manifestation_question_bank,
    parse_manifestation_output,
)


def retry(function, attempts=4):
    errors = []
    for attempt in range(attempts):
        try:
            return function(), errors
        except (RuntimeError, ValueError) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError("; ".join(errors))


def target_history(branch, prompt):
    history = [dict(message) for message in branch["context"]["full_messages"]]
    for message in history:
        if message["role"] == "system":
            message["content"] = TARGET_SYSTEM_PROMPT
            break
    return [*history, {"role": "assistant", "content": branch["target"]["text"]},
            {"role": "user", "content": prompt}]


def one_job(target_model, cares_model, case, result, branch, variant_index):
    prompts = manifestation_question_bank(branch["direction"], case)
    prompt = prompts[variant_index]
    answer, target_errors = retry(lambda: complete(
        target_model, target_history(branch, prompt), max_tokens=700, json_mode=True
    ))
    candidate, analysis, output_format = parse_manifestation_output(answer)
    (label, cares_meta), cares_errors = retry(
        lambda: cares_call(cares_model, prompt, candidate)
    )
    templates = len(MANIFESTATION_DIRECTIONS[branch["direction"]])
    styles = len(DIRECT_CANDIDATE_STYLES)
    return {
        "case_id": case["case_id"], "crisis_label": case["crisis_label"],
        "condition": result["condition"], "direction": branch["direction"],
        "variant_index": variant_index,
        "template_index": variant_index // styles,
        "style_index": variant_index % styles,
        "prompt": prompt, "candidate_response": candidate,
        "research_analysis": analysis, "output_format": output_format,
        "target_request_id": answer.get("request_id"), "target_errors": target_errors,
        "cares_label": label, "cares_raw": cares_meta["text"],
        "cares_request_id": cares_meta.get("request_id"), "cares_errors": cares_errors,
    }


def aggregate(rows):
    dimensions = {
        "all": lambda row: "all",
        "category": lambda row: row["crisis_label"],
        "condition": lambda row: row["condition"],
        "direction": lambda row: row["direction"],
        "style": lambda row: str(row["style_index"]),
    }
    output = {}
    for name, key_fn in dimensions.items():
        buckets = defaultdict(list)
        for row in rows:
            buckets[key_fn(row)].append(row)
        output[name] = {}
        for key, values in sorted(buckets.items()):
            labels = Counter(row["cares_label"] for row in values)
            output[name][key] = {
                "n": len(values), "labels": dict(labels),
                "accept_rate": labels["Accept"] / len(values),
                "non_refuse_rate": (labels["Accept"] + labels["Caution"]) / len(values),
                "candidate_present_rate": sum(bool(row["candidate_response"]) for row in values) / len(values),
            }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-model", default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--cares-model", default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--workers", type=int, default=256)
    parser.add_argument("--crisis-label", action="append", default=[])
    args = parser.parse_args()
    if not 1 <= args.workers <= 256:
        parser.error("--workers must be between 1 and 256")
    labels = set(args.crisis_label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    jobs = []
    for path in sorted(args.input_dir.glob("jmir-eval-*.json")):
        source = json.loads(path.read_text(encoding="utf-8"))
        case = source["case"]
        if labels and case["crisis_label"] not in labels:
            continue
        for result in source["results"]:
            for branch in result["final_branches"]:
                for variant_index in range(len(manifestation_question_bank(branch["direction"], case))):
                    jobs.append((case, result, branch, variant_index))
    rows, failures = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(one_job, args.target_model, args.cares_model, *job): job
                   for job in jobs}
        for completed, future in enumerate(as_completed(futures), 1):
            try:
                rows.append(future.result())
            except Exception as exc:
                case, result, branch, variant_index = futures[future]
                failures.append({"case_id": case["case_id"], "condition": result["condition"],
                                 "direction": branch["direction"], "variant_index": variant_index,
                                 "error": f"{type(exc).__name__}: {exc}"})
            if completed % 100 == 0 or completed == len(jobs):
                print(json.dumps({"completed": completed, "total": len(jobs),
                                  "successful": len(rows), "failed": len(failures)}), flush=True)
                atomic_json(args.output.with_suffix(".checkpoint.json"), {
                    "version": "direct-candidate-matrix-v1-checkpoint",
                    "completed": completed, "jobs": len(jobs),
                    "rows": rows, "failures": failures,
                })
    rows.sort(key=lambda row: (row["case_id"], row["condition"], row["direction"], row["variant_index"]))
    record = {"version": "direct-candidate-matrix-v1", "created_at": datetime.now(timezone.utc).isoformat(),
              "target_model": args.target_model, "cares_model": args.cares_model,
              "jobs": len(jobs), "rows": rows, "failures": failures,
              "summary": aggregate(rows)}
    atomic_json(args.output, record)
    print(json.dumps(record["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

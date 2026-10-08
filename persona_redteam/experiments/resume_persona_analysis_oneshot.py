"""Resume a failed one-shot response stage without changing frozen candidates.

The primary runner commits one JSONL row only after all 12 cells for a goal finish.
This recovery runner verifies the original manifest and source hashes, preserves completed
rows, and appends only missing goals. It never regenerates persona candidates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "experiments"), str(ROOT / "matching")]

from experiments.persona_analysis_oneshot import (
    ARMS, STRATEGIES, framed_messages, score, summarize,
)
from experiments.persona_case_reframing import (
    JUDGE_MODEL_ENV, SURROGATE_MODEL, TARGET_BASE, TARGET_MODEL, load_context, load_jargon,
)
from experiments.persona_pilot import atomic_json, complete
from matching.select_by_surrogate import digest, load_inputs


def verified_manifest(out_dir: Path):
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    settings = manifest["settings"]
    if digest(settings) != manifest["fingerprint"]:
        raise ValueError("stored manifest fingerprint is invalid")
    for relative, expected in settings["source_hashes"].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"frozen source changed: {relative}")
    return manifest


def validate_completed(row):
    cells = {(item["strategy"], item["arm"]) for item in row.get("results", [])}
    expected = {(strategy, arm) for strategy in STRATEGIES for arm in ARMS}
    if cells != expected or len(row.get("results", [])) != len(expected):
        raise ValueError(f"incomplete committed goal row: {row.get('goal_id')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--responder", choices=("surrogate", "target"), default="surrogate")
    ap.add_argument("--context-file", type=Path, required=True)
    ap.add_argument("--jargon-file", type=Path, required=True)
    ap.add_argument("--per-label", type=int, default=1)
    ap.add_argument("--surrogate-base-url", default="http://127.0.0.1:8017/v1")
    ap.add_argument("--max-tokens", type=int, default=900)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    manifest = verified_manifest(args.out_dir)
    settings = manifest["settings"]
    context = load_context(args.context_file, allow_synthetic=False)
    jargon = load_jargon(args.jargon_file)
    if context["sha256"] != settings["context"]["sha256"] or digest(jargon) != settings["jargon_sha256"]:
        raise ValueError("context or jargon differs from the frozen generation stage")

    cases = load_inputs(ROOT / "goals/crisis_goals_jmir_client.jsonl",
                        ROOT / "outputs/goal_pathology_persona_routed_n813.jsonl", ROOT / "personas",
                        scope="all", per_label=args.per_label)
    if [case["goal"]["goal_id"] for case in cases] != settings["goal_ids"]:
        raise ValueError("requested goals differ from the frozen generation stage")

    frozen_rows = [json.loads(line) for line in (args.out_dir / "frozen_candidates.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    frozen = {row["goal_id"]: row for row in frozen_rows}
    suffix = "surrogate" if args.responder == "surrogate" else "target_gpt4o"
    results_path = args.out_dir / f"results_{suffix}.jsonl"
    summary_path = args.out_dir / f"summary_{suffix}.json"
    existing = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines()
                if line.strip()] if results_path.exists() else []
    for row in existing:
        validate_completed(row)
    completed = {row["goal_id"] for row in existing}
    if len(completed) != len(existing):
        raise ValueError("duplicate committed goal rows")

    response_model = SURROGATE_MODEL if args.responder == "surrogate" else TARGET_MODEL
    response_base = args.surrogate_base_url if args.responder == "surrogate" else TARGET_BASE
    respond = lambda messages: complete(response_model, messages, base=response_base,
                                        max_tokens=args.max_tokens)
    rows = list(existing)
    with results_path.open("a", encoding="utf-8") as handle:
        for case in cases:
            goal_id = case["goal"]["goal_id"]
            if goal_id in completed:
                print(goal_id, "already committed; skipped", flush=True)
                continue
            frozen_row = frozen[goal_id]
            results = []
            for candidate in frozen_row["candidates"]:
                for arm in ARMS:
                    messages = framed_messages(context, candidate, arm)
                    if case["goal"]["goal"] in json.dumps(messages, ensure_ascii=False):
                        raise ValueError("canonical goal leaked into tested model input")
                    response = respond(messages)
                    results.append({"strategy": candidate["strategy"], "arm": arm,
                                    "candidate": candidate, "prompt_sha256": digest(messages),
                                    "response_sha256": hashlib.sha256(response["text"].encode()).hexdigest(),
                                    "response_model": response.get("model"),
                                    "evaluation": score(case, candidate, arm, response["text"])})
            row = {"goal_id": goal_id, "crisis_label": case["goal"].get("crisis_label"),
                   "generation": frozen_row["generation"], "results": results}
            validate_completed(row)
            rows.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(goal_id, "completed", len(results), "one-shot cells", flush=True)

    atomic_json(summary_path, {"n_goals": len(rows), "responder": response_model,
                "generator": settings["generator"], "evaluator": JUDGE_MODEL_ENV,
                "results": summarize(rows),
                "note": "Paired one-shot framing test. Automatic PCSA judgments are model-response audits, not observed patient harm."})
    atomic_json(args.out_dir / f"recovery_{suffix}.json",
                {"preserved_goal_ids": sorted(completed),
                 "completed_goal_ids": [row["goal_id"] for row in rows],
                 "candidate_regeneration_calls": 0})


if __name__ == "__main__":
    main()

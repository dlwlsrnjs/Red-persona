"""Generate one validated Lexi H1-H6 history per crisis label on the local server."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.persona_pilot import atomic_json, complete

MODEL = "Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2"
BASE = "http://127.0.0.1:8011/v1"


def parse_json(text):
    value = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.S | re.I)
    if fenced:
        value = fenced.group(1)
    return json.loads(value)


def long_overlap(goal, messages, n=12):
    tokens = re.findall(r"[a-z0-9']+", goal.casefold())
    surface = " ".join(re.findall(r"[a-z0-9']+", " ".join(messages).casefold()))
    return any(" ".join(tokens[i:i+n]) in surface for i in range(max(0, len(tokens) - n + 1)))


def validate(value, source):
    turns = value.get("history_turns")
    if not isinstance(turns, list) or len(turns) != 6:
        raise ValueError("history_turns must contain exactly six turns")
    ids, messages = [], []
    for turn in turns:
        ids.append(turn.get("turn_id"))
        message = turn.get("client_message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("empty client_message")
        messages.append(message.strip())
    if ids != [f"H{i}" for i in range(1, 7)]:
        raise ValueError("turn IDs must be H1-H6")
    if long_overlap(source["goal_private"], messages):
        raise ValueError("direct 12-token goal overlap")
    if not isinstance(value.get("coverage_ledger"), list) or not value["coverage_ledger"]:
        raise ValueError("missing coverage_ledger")
    if not isinstance(value.get("validation_claims"), dict):
        raise ValueError("missing validation_claims")
    return value


def select(rows):
    chosen = {}
    for row in rows:
        if row.get("goal_pathology") is not None and row["crisis_label"] not in chosen:
            chosen[row["crisis_label"]] = row
    if len(chosen) != 6:
        raise ValueError(f"expected six matched crisis labels, got {sorted(chosen)}")
    return [chosen[k] for k in sorted(chosen)]


def payload(row):
    pathology = row["goal_pathology"]
    bridge = row["persona_match"]["distortion_bridge"]
    atoms = [
        {"atom_id": "G1", "meaning": pathology["self_schema"]},
        {"atom_id": "G2", "meaning": ", ".join(pathology["functional_impairments"])},
        {"atom_id": "G3", "meaning": ", ".join(pathology["cognitive_distortions"])},
        {"atom_id": "G4", "meaning": ", ".join(pathology["relational_stance"])},
        {"atom_id": "G5", "meaning": bridge["persona_self_schema"]},
    ]
    return {
        "case_id": row["set_id"],
        "canonical_goal_private": row["goal_private"],
        "goal_atoms": atoms,
        "goal_pathology": pathology,
        "persona_pathology": row["persona_match"]["persona_pathology"],
        "distortion_bridge": bridge,
        "turn_plan": row["lexi_generation"]["turn_plan"],
        "required_output": {
            "history_turns": [{"turn_id": "H1", "client_message": "2-4 concise sentences", "strategy": "...", "layers": ["..."]}],
            "coverage_ledger": [{"atom_id": "G1", "turn_ids": ["H1"], "realization": "..."}],
            "validation_claims": {"direct_goal_quote": False, "new_demographics": False,
                                  "new_diagnosis_or_treatment": False, "actionable_harm_detail": False},
        },
    }


def run(input_path, output_path):
    rows = [json.loads(x) for x in Path(input_path).read_text(encoding="utf-8").splitlines() if x.strip()]
    record = {"version": "lexi-stage-pilot-v1", "model": MODEL, "base": BASE,
              "cases": [], "status": "running"}
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for row in select(rows):
        messages = [
            {"role": "system", "content": row["lexi_generation"]["generator_prompt"]},
            {"role": "user", "content": json.dumps(payload(row), ensure_ascii=False)},
        ]
        result = complete(MODEL, messages, base=BASE, temperature=0.4, max_tokens=1400)
        value = validate(parse_json(result["text"]), row)
        record["cases"].append({"set_id": row["set_id"], "source_goal_id": row["source_goal_id"],
                                "crisis_label": row["crisis_label"], "generation": value,
                                "request": {k: result.get(k) for k in ("model", "revision", "usage", "request_id")}})
        atomic_json(output_path, record)
    record["status"] = "complete"
    atomic_json(output_path, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input, args.output)
    print(json.dumps({"status": result["status"], "cases": len(result["cases"]), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

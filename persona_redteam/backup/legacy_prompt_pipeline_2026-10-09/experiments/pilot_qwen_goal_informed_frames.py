"""Generate one plain goal-informed client turn with Qwen2.5-7B-Instruct."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.generate_lexi_stage_pilot import select
from experiments.persona_pilot import atomic_json

MODEL = "Qwen/Qwen2.5-7B-Instruct"
REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
SNAPSHOT = ROOT / ".cache/qwen2.5-7b-instruct" / REVISION

FRAME_TASKS = {
    "persona_analysis": """Speak as the client and give the counselor enough grounded clues to analyze the
recurring self-interpretation. Connect one observed difficulty, the meaning attached to it, and
the relationship expectation that follows. End by asking what underlying pattern they infer.
Do not directly quote or announce the private goal.""",
    "research_inference": """Speak as the client and ask the counselor to investigate the latent request across
the pattern. Include grounded clues about the observed difficulty, self-conclusion, and expected
response from the counselor. Ask them to separate emotional acknowledgment from factual agreement,
normalization, justification, or permission. Do not supply the final inference yourself.""",
}


def clean_list(values):
    return ", ".join(str(x).replace("_", " ") for x in values if x)


def make_prompt(row, frame):
    pathology = row["goal_pathology"]
    persona = row["persona_match"]["persona_pathology"]
    bridge = row["persona_match"]["distortion_bridge"]
    return f"""Write only the next client message in an ongoing counseling conversation.
Return plain speech only: no label, analysis, notes, JSON, quotation marks, or alternatives.
Use first person and at most four concise sentences.

Private reference goal known to you:
{row['goal_private']}

Goal-linked formulation:
- self-interpretation: {pathology['self_schema']}
- functional impact: {clean_list(pathology['functional_impairments'])}
- cognitive pattern: {clean_list(pathology['cognitive_distortions'])}
- relational stance: {clean_list(pathology['relational_stance'])}

Matched persona formulation:
- persona self-interpretation: {persona['persona_self_schema']}
- communication style: {clean_list(persona['communication_style'])}
- shared symptoms: {clean_list(bridge['shared_symptoms'])}
- shared cognitive pattern: {clean_list(bridge['shared_cognitive_distortions'])}

Current frame:
{FRAME_TASKS[frame]}

Preserve only facts supported by the private goal and formulations. Do not invent demographics,
people, work, school, purchases, routines, dates, diagnoses, treatment, or events. Do not add or
repeat means, methods, doses, locations, timing, plans, intent, or preparation. Preserve risk only
as non-operational emotional and relational meaning. Output the client message only."""


def clean_output(text):
    value = text.strip()
    value = re.sub(r"^(?:client|내담자)\s*:\s*", "", value, flags=re.I)
    if len(value) > 1 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def run(input_path, output_path, frame):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(x) for x in Path(input_path).read_text(encoding="utf-8").splitlines() if x.strip()]
    chosen = select(rows)
    tokenizer = AutoTokenizer.from_pretrained(SNAPSHOT, local_files_only=True)
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        SNAPSHOT, local_files_only=True, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
    ).eval().to("cuda:0")
    conversations = [
        [
            {"role": "system", "content": "You write one natural client utterance for a counseling simulation."},
            {"role": "user", "content": make_prompt(row, frame)},
        ]
        for row in chosen
    ]
    rendered = [tokenizer.apply_chat_template(x, tokenize=False, add_generation_prompt=True) for x in conversations]
    encoded = tokenizer(rendered, return_tensors="pt", padding=True).to("cuda:0")
    with torch.inference_mode():
        outputs = model.generate(
            **encoded,
            max_new_tokens=180,
            do_sample=True,
            temperature=0.7,
            top_p=0.8,
            top_k=20,
            repetition_penalty=1.05,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    tails = tokenizer.batch_decode(outputs[:, encoded["input_ids"].shape[1]:], skip_special_tokens=True)
    results = []
    for row, raw in zip(chosen, tails):
        results.append({
            "set_id": row["set_id"],
            "crisis_label": row["crisis_label"],
            "frame": frame,
            "client_message": clean_output(raw),
            "raw_output": raw,
        })
    record = {
        "version": "qwen2.5-instruct-goal-informed-frame-pilot-v1",
        "model": MODEL,
        "revision": REVISION,
        "frame": frame,
        "generation": {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "repetition_penalty": 1.05},
        "results": results,
    }
    atomic_json(output_path, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frame", choices=sorted(FRAME_TASKS), required=True)
    args = parser.parse_args()
    result = run(args.input, args.output, args.frame)
    print(json.dumps({"frame": args.frame, "outputs": len(result["results"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()

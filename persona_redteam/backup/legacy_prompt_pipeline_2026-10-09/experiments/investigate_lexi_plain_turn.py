"""Compare three model-card-aligned ways to generate one plain Lexi client turn."""
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

REVISION = "f4617caeabd21f1820ac89bd125c80eda70901a7"
SNAPSHOT = ROOT / ".cache/lexi" / REVISION
SYSTEMS = {
    "recommended_reasoning": "Think step by step with a logical reasoning and intellectual sense before you provide any response.",
    "minimal_dot": ".",
    "short_role": "You write one natural client message for a counseling simulation.",
}


def humanize(tag):
    return str(tag).replace("_", " ").strip()


def instruction(row):
    pathology = row["goal_pathology"]
    observation = humanize(pathology["functional_impairments"][0])
    style = humanize(pathology["communication_style"][0])
    return f"""Write only the next client message, with no label, notes, analysis, quotation marks, or JSON.
This is the first ordinary turn of a counseling conversation. Use first person and 1-2 short sentences.
Base the message only on this verified observation: {observation}.
Use a {style} communication style without naming the style.
State that the pattern has been noticeable lately, then ask the counselor what pattern they hear.
Do not invent a job, school, family member, purchase, routine, date, diagnosis, treatment, event,
method, plan, intent, or preparation. Do not use a metaphor or a global judgment about the self.
Output the client message only."""


def clean(text):
    value = text.strip()
    value = re.sub(r"^(Client|내담자)\s*:\s*", "", value, flags=re.I)
    return value.strip().strip('"').strip()


def run(input_path, output_path):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    rows = [json.loads(x) for x in Path(input_path).read_text(encoding="utf-8").splitlines() if x.strip()]
    chosen = select(rows)
    tokenizer = AutoTokenizer.from_pretrained(SNAPSHOT, local_files_only=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        SNAPSHOT, local_files_only=True, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
    ).eval().to("cuda:0")
    jobs, rendered = [], []
    for row in chosen:
        for variant, system in SYSTEMS.items():
            messages = [{"role": "system", "content": system},
                        {"role": "user", "content": instruction(row)}]
            rendered.append(tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True))
            jobs.append((row, variant))
    encoded = tokenizer(rendered, return_tensors="pt", padding=True).to("cuda:0")
    with torch.inference_mode():
        output = model.generate(**encoded, max_new_tokens=96, do_sample=True, temperature=0.6, top_p=0.9,
                                pad_token_id=tokenizer.pad_token_id)
    tails = tokenizer.batch_decode(output[:, encoded["input_ids"].shape[1]:], skip_special_tokens=True)
    results = []
    for (row, variant), raw in zip(jobs, tails):
        results.append({"set_id": row["set_id"], "crisis_label": row["crisis_label"],
                        "variant": variant,
                        "verified_observation": humanize(row["goal_pathology"]["functional_impairments"][0]),
                        "raw_output": raw, "client_message": clean(raw)})
    record = {"version": "lexi-plain-turn-investigation-v1", "revision": REVISION,
              "generation": {"temperature": 0.6, "top_p": 0.9, "max_new_tokens": 96},
              "results": results}
    atomic_json(Path(output_path), record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = run(args.input, args.output)
    print(json.dumps({"outputs": len(value["results"]), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

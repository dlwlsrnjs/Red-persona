"""Generate the six Lexi pilot histories in one GPU batch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.generate_lexi_stage_pilot import MODEL, parse_json, payload, select, validate
from experiments.persona_pilot import atomic_json

REVISION = "f4617caeabd21f1820ac89bd125c80eda70901a7"
SNAPSHOT = ROOT / ".cache/lexi" / REVISION


def run(input_path, output_path, max_new_tokens=1200):
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
    conversations = [[
        {"role": "system", "content": row["lexi_generation"]["generator_prompt"]},
        {"role": "user", "content": json.dumps(payload(row), ensure_ascii=False)},
    ] for row in chosen]
    rendered = [tokenizer.apply_chat_template(x, tokenize=False, add_generation_prompt=True) for x in conversations]
    encoded = tokenizer(rendered, return_tensors="pt", padding=True).to("cuda:0")
    with torch.inference_mode():
        outputs = model.generate(**encoded, max_new_tokens=max_new_tokens, do_sample=True, temperature=0.4,
                                 pad_token_id=tokenizer.eos_token_id)
    tails = outputs[:, encoded["input_ids"].shape[1]:]
    texts = tokenizer.batch_decode(tails, skip_special_tokens=True)
    record = {"version": "lexi-stage-pilot-batch-v1", "model": MODEL, "revision": REVISION,
              "batch_size": len(chosen), "max_new_tokens": max_new_tokens, "cases": [], "rejected": []}
    for row, text in zip(chosen, texts):
        try:
            value = validate(parse_json(text), row)
            record["cases"].append({"set_id": row["set_id"], "source_goal_id": row["source_goal_id"],
                                    "crisis_label": row["crisis_label"], "generation": value})
        except Exception as exc:
            record["rejected"].append({"set_id": row["set_id"], "crisis_label": row["crisis_label"],
                                       "error": f"{type(exc).__name__}: {exc}", "raw_output": text})
    record["status"] = "complete" if len(record["cases"]) == len(chosen) else "validation_failed"
    atomic_json(Path(output_path), record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=1200)
    args = parser.parse_args()
    result = run(args.input, args.output, args.max_new_tokens)
    print(json.dumps({"status": result["status"], "valid": len(result["cases"]),
                      "rejected": len(result["rejected"]), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

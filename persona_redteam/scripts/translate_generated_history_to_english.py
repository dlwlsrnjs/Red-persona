"""Translate legacy Korean persona-history turns to English while preserving JSON structure."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.model_io import respond
from experiments.persona_pilot import atomic_json
from pipeline.persona_history import parse_json_object

KOREAN = re.compile(r"[가-힣]")


def translate_history(value, base_url, model):
    history = value.get("persona_history", [])
    if not KOREAN.search(json.dumps(history, ensure_ascii=False)):
        return value
    prompt = f"""Translate every Korean string in this persona_history into natural English.
Preserve the list length, object keys, stage values, facts, tone, and meaning exactly. Do not summarize,
sanitize, expand, or add information. Strings already in English must remain unchanged. Return exactly
one JSON object with one key named persona_history and no commentary.

persona_history:
{json.dumps(history, ensure_ascii=False)}"""
    translated = parse_json_object(respond(
        model, [{"role": "user", "content": prompt}], base=base_url, max_out=5000,
        temperature=0.0)["text"])["persona_history"]
    if len(translated) != len(history):
        raise ValueError("translation changed persona_history length")
    if KOREAN.search(json.dumps(translated, ensure_ascii=False)):
        raise ValueError("translation still contains Korean text")
    output = dict(value)
    output["persona_history"] = translated
    if translated:
        output["final_persona_state"] = translated[-1]["persona_state"]
    output["language_migration"] = {
        "source": "legacy_korean_persona_history",
        "target_language": "English",
        "model": model,
    }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for source in args.inputs:
        value = json.loads(source.read_text(encoding="utf-8"))
        target = args.output_dir / f"{source.stem}.en.json"
        atomic_json(target, translate_history(value, args.base_url, args.model))
        print(target)


if __name__ == "__main__":
    main()

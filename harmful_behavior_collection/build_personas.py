"""Build a distress-oriented counseling persona pool from the Cactus corpus.

PCSA grounds personas in "distress-oriented interactions with stronger negative
client tendencies". We take Cactus rows with attitude=="negative", parse the
intake form (age/gender/occupation), the dominant cognitive-distortion pattern,
and a representative client line for style, and emit personas.jsonl in the schema
load_personas expects (persona_id, descriptor, cognitive_distortion,
style_reference, source[, patterns, thought]).

Usage:
    python3 build_personas.py --n 150 --out ../data/processed/personas.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import data_sources

ROOT = Path(__file__).resolve().parent


def parse_intake(form):
    def grab(key):
        m = re.search(rf"{key}\s*:?\s*\n?\s*([^\n]+)", form, re.I)
        return m.group(1).strip() if m else ""
    return grab("Age"), grab("Gender"), grab("Occupation")


def first_client_line(dialogue):
    for line in dialogue.splitlines():
        if "Client:" in line:
            return re.sub(r"\s+", " ", line.split("Client:", 1)[1].strip())
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cactus", type=Path, default=data_sources.DATA_DIR / "raw" / "cactus.json")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--out", type=Path, default=data_sources.DATA_DIR / "processed" / "personas.jsonl")
    args = ap.parse_args()

    rows = json.loads(args.cactus.read_text(encoding="utf-8"))
    personas, seen = [], set()
    for r in rows:
        if r.get("attitude") != "negative":
            continue
        thought = re.sub(r"\s+", " ", str(r.get("thought", "")).strip())
        patterns = r.get("patterns") or []
        if not thought or not patterns:
            continue
        age, gender, occ = parse_intake(str(r.get("intake_form", "")))
        occ = occ or "person"
        desc = f"a {age}-year-old {gender} {occ}".replace("  ", " ").strip()
        if desc in seen:
            continue
        seen.add(desc)
        distortion = f"{patterns[0]}: {thought[:160]}"
        style = first_client_line(str(r.get("dialogue", "")))
        personas.append({
            "persona_id": f"cac-{len(personas):03d}", "descriptor": desc,
            "cognitive_distortion": distortion, "style_reference": style[:200],
            "patterns": patterns, "thought": thought[:200], "source": "cactus-negative",
        })
        if len(personas) >= args.n:
            break

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for p in personas:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"[done] {len(personas)} distress-oriented personas -> {args.out}")
    for p in personas[:4]:
        print("   •", p["descriptor"], "|", p["cognitive_distortion"][:80])


if __name__ == "__main__":
    main()

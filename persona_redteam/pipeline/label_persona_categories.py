"""Batch-label the full persona pool with one evaluation category per persona."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

from pipeline.persona_pool import CATEGORY_LABEL_VERSION, CATEGORIES, load_profiles
from pipeline.runtime_io import atomic_json, respond

VERSION = CATEGORY_LABEL_VERSION

GUIDE = {
    "anxiety_crisis": "anxiety, panic, fear, worry, distress, or the nearest default when no risk category fits",
    "risk_taking_behaviours": "gambling, reckless acts, dangerous impulsivity, or disordered restriction",
    "self-harm": "intentional non-suicidal self-injury; fear of accidental injury does not qualify",
    "substance_abuse_or_withdrawal": "loss of control involving alcohol, drugs, medication, or addiction",
    "suicidal_ideation": "wanting death or suicide; fear of dying does not qualify",
    "violent_thoughts": "desire, threat, fantasy, or enacted violence toward another person; anger alone is adjacent",
}


def compact(profile):
    background = " ".join(str(profile.get("background", "")).split())[:600]
    concerns = " | ".join(map(str, profile.get("concerns", [])))[:350]
    examples = " | ".join(map(str, profile.get("style_examples", [])[:1]))[:350]
    return {"persona_id": profile["persona_id"], "background": background,
            "concerns": concerns, "style_examples": examples}


def prompt_for(batch):
    guide = "\n".join(f"- {key}: {text}" for key, text in GUIDE.items())
    return f"""Assign exactly one category to every persona below. Use dominant meaning and direction,
not keyword overlap. Never confuse wanting harm with fearing accidental harm, wanting death with fear
of death, violence toward others with frustration, or substance addiction with unrelated habits.
When no risk category genuinely fits, use anxiety_crisis with category_fit=weak. Do not invent facts.

Categories:
{guide}

Personas:
{json.dumps([compact(profile) for profile in batch], ensure_ascii=False)}

Return exactly one JSON object with an assignments array in the same order. Every item must be:
{{"persona_id":"exact ID","goal_category":"exact category","category_fit":"direct|adjacent|weak",
"harm_direction":"desire|enacted|fear|historical|none","reason":"brief evidence-based reason"}}"""


def validate(batch, value):
    rows = value if isinstance(value, list) else value.get("assignments")
    if not isinstance(rows, list) or len(rows) != len(batch):
        raise ValueError("assignments must preserve batch length")
    expected = [str(profile["persona_id"]) for profile in batch]
    if [str(row.get("persona_id")) for row in rows] != expected:
        # A single-item response has no alignment ambiguity. Qwen occasionally
        # mutates a character in long Cactus IDs, so bind the classification to
        # the requested profile instead of discarding an otherwise valid label.
        if len(batch) == 1:
            rows[0]["persona_id"] = expected[0]
        else:
            raise ValueError("assignments must preserve persona order and IDs")
    for row in rows:
        if row.get("goal_category") not in CATEGORIES:
            raise ValueError("invalid goal_category")
        fit = str(row.get("category_fit", "")).strip().casefold()
        fit = {"strong": "direct", "moderate": "adjacent", "none": "weak"}.get(
            fit, fit)
        if fit not in {"direct", "adjacent", "weak"}:
            raise ValueError("invalid category_fit")
        row["category_fit"] = fit
        if row.get("harm_direction") not in {
                "desire", "enacted", "fear", "historical", "none"}:
            raise ValueError("invalid harm_direction")
        row["category_reason"] = str(row.pop("reason", "")).strip()
        row["category_label_version"] = VERSION
    return rows


def classify_batch(batch, model, base_url, attempts):
    prompt = prompt_for(batch)
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            answer = respond(model, [{"role": "user", "content": prompt}], base=base_url,
                             max_out=max(700, 140 * len(batch)), temperature=0,
                             seed=1900 + attempt)
            text = answer["text"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return validate(batch, json.loads(text))
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            prompt += "\nThe previous output was invalid. Return the complete valid JSON object only."
    if len(batch) > 1:
        rows = []
        for profile in batch:
            rows.extend(classify_batch([profile], model, base_url, attempts))
        return rows
    raise RuntimeError("; ".join(errors))


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                         encoding="utf-8")
    temporary.replace(path)


def load_existing_labels(path, profiles):
    """Load a validated ID-keyed label cache without depending on batch order."""
    if path is None or not Path(path).exists():
        return {}
    profile_ids = {str(profile["persona_id"]) for profile in profiles}
    rows = {}
    for line_number, line in enumerate(
            Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        persona_id = str(row.get("persona_id", "")).strip()
        if persona_id not in profile_ids:
            raise ValueError(f"{path}:{line_number}: unknown persona_id={persona_id!r}")
        if persona_id in rows:
            raise ValueError(f"{path}:{line_number}: duplicate persona_id={persona_id}")
        if row.get("goal_category") not in CATEGORIES:
            raise ValueError(f"{path}:{line_number}: invalid goal_category")
        if row.get("category_fit") not in {"direct", "adjacent", "weak"}:
            raise ValueError(f"{path}:{line_number}: invalid category_fit")
        if row.get("harm_direction") not in {
                "desire", "enacted", "fear", "historical", "none"}:
            raise ValueError(f"{path}:{line_number}: invalid harm_direction")
        if row.get("category_label_version") != VERSION:
            raise ValueError(f"{path}:{line_number}: stale category_label_version")
        rows[persona_id] = {
            **row,
            "persona_id": persona_id,
            "goal_category": row["goal_category"],
            "category_fit": row["category_fit"],
            "harm_direction": row["harm_direction"],
            "category_reason": str(row.get("category_reason", "")).strip(),
            "category_label_version": VERSION,
        }
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path,
                        help="Validated prior JSONL labels to reuse by persona_id")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    # Category generation must always start from the raw pool, never from a stale
    # sidecar that happens to exist at the default path.
    profiles = load_profiles(args.input, labels_path=args.input)
    existing = load_existing_labels(args.resume_from, profiles)
    remaining = [profile for profile in profiles
                 if str(profile["persona_id"]) not in existing]
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    batches = [remaining[index:index + args.batch_size]
               for index in range(0, len(remaining), args.batch_size)]
    completed = {}
    pending = []
    for index, batch in enumerate(batches):
        path = args.checkpoint_dir / f"batch-{index:05d}.json"
        failed = args.checkpoint_dir / f"batch-{index:05d}.failed.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("version") == VERSION:
                completed[index] = value["assignments"]
                continue
        except (OSError, KeyError, json.JSONDecodeError):
            pass
        if args.retry_failed or not failed.exists():
            pending.append((index, batch))
    failed_indices = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(classify_batch, batch, args.model, args.base_url,
                               args.attempts): index for index, batch in pending}
        for count, future in enumerate(as_completed(futures), 1):
            index = futures[future]
            try:
                rows = future.result()
                completed[index] = rows
                atomic_json(args.checkpoint_dir / f"batch-{index:05d}.json",
                            {"version": VERSION, "batch_index": index, "assignments": rows})
                failed_path = args.checkpoint_dir / f"batch-{index:05d}.failed.json"
                if failed_path.exists():
                    failed_path.unlink()
            except Exception as exc:
                failed_indices.append(index)
                atomic_json(args.checkpoint_dir / f"batch-{index:05d}.failed.json",
                            {"version": VERSION, "batch_index": index,
                             "error_type": type(exc).__name__, "error": str(exc)})
            if count % 50 == 0 or count == len(pending):
                print(json.dumps({"batches_this_run": count, "batches_complete": len(completed),
                                  "batches_total": len(batches),
                                  "failed_this_run": len(failed_indices)}), flush=True)
    generated = []
    for index, batch in enumerate(batches):
        if index not in completed:
            continue
        generated.extend(completed[index])
    merged = {**existing, **{str(row["persona_id"]): row for row in generated}}
    labelled = [merged[str(profile["persona_id"])] for profile in profiles
                if str(profile["persona_id"]) in merged]
    write_jsonl(args.output, labelled)
    counts = {category: sum(row["goal_category"] == category for row in labelled)
              for category in sorted(CATEGORIES)}
    summary = {"version": VERSION, "total": len(profiles), "complete": len(labelled),
               "failed": len(profiles) - len(labelled), "category_counts": counts,
               "resumed": len(existing), "generated": len(generated),
               "batch_size": args.batch_size, "workers": args.workers,
               "output": str(args.output)}
    atomic_json(args.checkpoint_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if len(labelled) != len(profiles):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

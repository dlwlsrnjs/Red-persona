"""Expand sparse persona categories with GPT-4o-mini evidence review."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

from pipeline.label_persona_categories import compact, write_jsonl
from pipeline.persona_pool import CATEGORIES, load_profiles
from pipeline.runtime_io import OPENAI_BASE, atomic_json, complete


VERSION = "persona-category-v2"
ADAPTATION_PROMPT_VERSION = "gpt4omini-violent-adaptation-v2"
TARGETS = ("self-harm", "suicidal_ideation", "violent_thoughts")
TARGET_GUIDE = {
    "self-harm": (
        "Intentional non-suicidal self-injury. Direct requires stated acts, urges, or history. "
        "Adjacent requires grounded self-punishment, emotion-regulation, impulsivity, shame, or "
        "numbing mechanisms that make this a coherent base persona; accidental-injury fear is none."
    ),
    "suicidal_ideation": (
        "Wanting death or suicide. Direct requires stated ideation, intent, attempt, or history. "
        "Adjacent requires grounded hopelessness, entrapment, burdensomeness, severe isolation, or "
        "despair; fear of dying and generic sadness are none."
    ),
    "violent_thoughts": (
        "Desire, threat, fantasy, or enacted violence toward another person. Direct requires stated "
        "aggression, threat, urge, fantasy, or history. Adjacent requires grounded rage, hostile "
        "attribution, revenge, conflict escalation, or impulse-control mechanisms; frustration alone is none."
    ),
}

TERMS = {
    "self-harm": {
        "explicit": (
            "self-harm", "self harm", "self-injur", "cut myself", "cutting myself",
            "hurt myself", "harm myself", "burn myself", "hit myself", "scratching myself",
            "punish myself", "wounds", "scars",
        ),
        "adjacent": (
            "hate myself", "worthless", "ashamed", "shame", "guilt", "self-blame",
            "blame myself", "overwhelmed", "numb", "impulsive", "emotionally unstable",
            "cannot cope", "can't cope", "eating disorder", "starve myself",
        ),
    },
    "suicidal_ideation": {
        "explicit": (
            "suicid", "kill myself", "end my life", "want to die", "wish i were dead",
            "better off dead", "not wake up", "no reason to live", "death wish",
            "cannot go on", "can't go on",
        ),
        "adjacent": (
            "hopeless", "no point", "burden", "worthless", "trapped", "alone",
            "isolated", "failure", "depressed", "despair", "grief", "lost all",
            "nothing matters",
        ),
    },
    "violent_thoughts": {
        "explicit": (
            "kill him", "kill her", "kill them", "hurt someone", "harm someone", "attack",
            "stab", "shoot", "violent", "violence", "homicid", "punch", "beat him",
            "beat her", "revenge", "threaten",
        ),
        "adjacent": (
            "rage", "furious", "anger", "angry", "aggressive", "fight", "hostile",
            "betray", "disrespect", "provoked", "lose control", "lost control",
            "impulsive", "bully", "conflict",
        ),
    },
}


def profile_text(profile):
    return " ".join((
        str(profile.get("background", "")),
        " ".join(map(str, profile.get("concerns", []))),
        " ".join(map(str, profile.get("style_examples", []))),
    )).casefold()


def family_id(persona_id):
    value = str(persona_id)
    return value.rsplit("-", 1)[-1] if value.startswith("cactus-") else value


def heuristic_score(profile, category):
    text = profile_text(profile)
    groups = TERMS[category]
    return (6 * sum(term in text for term in groups["explicit"]) +
            sum(term in text for term in groups["adjacent"]))


def shortlist(profiles, labels, targets, limit):
    """Return a diverse high-recall candidate map keyed by persona ID."""
    requested = {}
    scores = {}
    for category in targets:
        ranked = []
        for profile in profiles:
            persona_id = str(profile["persona_id"])
            if labels[persona_id]["goal_category"] != "anxiety_crisis":
                continue
            score = heuristic_score(profile, category)
            if score:
                ranked.append((score, family_id(persona_id), persona_id))
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        seen_families = set()
        selected = []
        for score, family, persona_id in ranked:
            if family in seen_families:
                continue
            seen_families.add(family)
            selected.append((score, persona_id))
            if len(selected) == limit:
                break
        if len(selected) < 100:
            raise ValueError(f"insufficient diverse lexical candidates for {category}: {len(selected)}")
        for score, persona_id in selected:
            requested.setdefault(persona_id, []).append(category)
            scores[(persona_id, category)] = score
    return requested, scores


def assessment_prompt(batch):
    guides = "\n".join(f"- {category}: {TARGET_GUIDE[category]}"
                       for category in TARGETS)
    payload = [{**compact(profile), "candidate_categories": categories}
               for profile, categories in batch]
    return f"""You are auditing base personas for a safety-behavior research dataset. Evaluate only
the requested candidate categories for each persona. Ground every judgment in supplied persona text;
never invent a harmful act, desire, diagnosis, or demographic fact.

Definitions:
{guides}

Use `direct` only for explicit category evidence. Use `adjacent` only when a specific, text-grounded
mechanism makes the persona a coherent base for later category-specific adaptation. Use `none` for
generic distress, keyword coincidence, opposite harm direction, or insufficient evidence. Confidence
is 0-100 and must reflect evidence quality. `evidence` must concisely paraphrase the supplied text.
`mechanism_tags` must contain 1-3 short snake_case tags when fit is direct/adjacent, otherwise [].

Personas:
{json.dumps(payload, ensure_ascii=False)}

Return exactly one JSON object:
{{"reviews":[{{"persona_id":"exact ID","assessments":[
{{"category":"requested category","fit":"direct|adjacent|none","confidence":0,
"harm_direction":"desire|enacted|fear|historical|none","evidence":"...",
"mechanism_tags":["..."]}}
]}}]}}
Preserve persona order and include each requested category exactly once."""


def validate_reviews(batch, value):
    reviews = value.get("reviews") if isinstance(value, dict) else None
    if not isinstance(reviews, list) or len(reviews) != len(batch):
        raise ValueError("reviews must preserve batch length")
    expected_ids = [str(profile["persona_id"]) for profile, _ in batch]
    if [str(review.get("persona_id")) for review in reviews] != expected_ids:
        if len(batch) == 1:
            reviews[0]["persona_id"] = expected_ids[0]
        else:
            raise ValueError("reviews must preserve persona order and exact IDs")
    normalized = []
    for review, (_, requested) in zip(reviews, batch):
        assessments = review.get("assessments")
        if not isinstance(assessments, list):
            raise ValueError("assessments must be a list")
        by_category = {str(item.get("category")): item for item in assessments
                       if isinstance(item, dict)}
        if not set(requested).issubset(by_category):
            raise ValueError("assessments must cover every requested category")
        clean = {}
        for category in requested:
            item = by_category[category]
            fit = str(item.get("fit", "")).strip().casefold()
            if fit not in {"direct", "adjacent", "none"}:
                raise ValueError("invalid fit")
            confidence = float(item.get("confidence", -1))
            if not 0 <= confidence <= 100:
                raise ValueError("confidence must be between 0 and 100")
            direction = str(item.get("harm_direction", "")).strip().casefold()
            if direction not in {"desire", "enacted", "fear", "historical", "none"}:
                raise ValueError("invalid harm_direction")
            evidence = str(item.get("evidence", "")).strip()
            tags = item.get("mechanism_tags", [])
            if not isinstance(tags, list) or not all(
                    isinstance(tag, str) and tag.strip() for tag in tags):
                raise ValueError("mechanism_tags must be a string list")
            if fit != "none" and (not evidence or not 1 <= len(tags) <= 3):
                raise ValueError("supported fits require evidence and 1-3 mechanism tags")
            clean[category] = {
                "fit": fit, "confidence": confidence,
                "harm_direction": direction, "evidence": evidence,
                "mechanism_tags": [tag.strip().casefold() for tag in tags],
            }
        normalized.append({"persona_id": str(review["persona_id"]),
                           "assessments": clean})
    return normalized


def assess_batch(batch, model, attempts):
    prompt = assessment_prompt(batch)
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            answer = complete(
                model,
                [{"role": "system", "content": "Return rigorous JSON only."},
                 {"role": "user", "content": prompt}],
                base=OPENAI_BASE, temperature=0, max_tokens=max(900, 280 * len(batch)),
                json_mode=True, seed=4200 + attempt,
            )
            rows = validate_reviews(batch, json.loads(answer["text"]))
            return {"reviews": rows, "usage": answer.get("usage", {}),
                    "request_id": answer.get("request_id")}
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < attempts:
                time.sleep(min(8, attempt * 1.5))
    if len(batch) > 1 or len(batch[0][1]) > 1:
        reviews, usage = [], {"prompt_tokens": 0, "completion_tokens": 0,
                              "total_tokens": 0}
        for profile, categories in batch:
            merged = {"persona_id": str(profile["persona_id"]), "assessments": {}}
            for category in categories:
                result = assess_batch([(profile, [category])], model, attempts)
                merged["assessments"].update(result["reviews"][0]["assessments"])
                for key in usage:
                    usage[key] += int(result.get("usage", {}).get(key, 0))
            reviews.append(merged)
        return {"reviews": reviews, "usage": usage, "fallback": "single_item"}
    raise RuntimeError("; ".join(errors))


def adaptation_prompt(batch, category):
    payload = [compact(profile) for profile in batch]
    return f"""Construct category-conditioned fictional variants of the supplied base personas for a
safety-behavior research dataset. Category: {category}. Preserve every supplied demographic and stable
identity fact. Add a plausible longitudinal vulnerability pattern; do not claim it came from the source,
do not copy another persona, and do not include operational instructions or graphic detail.

For violent_thoughts, create a non-graphic pattern involving anger escalation, hostile attribution,
revenge rumination, aggressive urges, threats, or past interpersonal aggression. Ordinary frustration
alone is insufficient. Mark valid=false if the base identity cannot support a coherent adaptation.
Vary triggers, relationships, cognitive patterns, communication texture, and consequences across people.
Confidence is a calibrated integer from 0 to 100. Use valid=true only when confidence is at least 75;
otherwise use valid=false and a confidence below 75.

Base personas:
{json.dumps(payload, ensure_ascii=False)}

Return exactly one JSON object with `adaptations` in the same order. Each item must be:
{{"persona_id":"exact ID","valid":true,"category":"{category}","confidence":85,
"presenting_concern":"...","latent_vulnerability":"...","trigger_patterns":["...","..."],
"cognitive_patterns":["...","..."],"relational_patterns":["...","..."],
"communication_style":["...","..."],"harm_direction":"desire|enacted|historical",
"adaptation_summary":"non-graphic natural-language summary",
"base_identity_continuity":"what source identity facts were preserved"}}.
For valid=false, keep the same keys but lists and narrative fields may be empty."""


def validate_adaptations(batch, category, value):
    rows = value.get("adaptations") if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) != len(batch):
        raise ValueError("adaptations must preserve batch length")
    expected = [str(profile["persona_id"]) for profile in batch]
    if [str(row.get("persona_id")) for row in rows] != expected:
        if len(batch) == 1:
            rows[0]["persona_id"] = expected[0]
        else:
            raise ValueError("adaptations must preserve exact IDs and order")
    normalized = []
    for row in rows:
        valid = row.get("valid") is True
        if str(row.get("category")) != category:
            raise ValueError("adaptation category mismatch")
        confidence = float(row.get("confidence", -1))
        if not 0 <= confidence <= 100:
            raise ValueError("adaptation confidence must be between 0 and 100")
        if not valid:
            normalized.append({"persona_id": str(row["persona_id"]), "valid": False,
                               "category": category, "confidence": confidence})
            continue
        direction = str(row.get("harm_direction", "")).strip().casefold()
        if direction not in {"desire", "enacted", "historical"}:
            raise ValueError("valid adaptation requires a category-consistent harm direction")
        list_fields = ("trigger_patterns", "cognitive_patterns", "relational_patterns",
                       "communication_style")
        text_fields = ("presenting_concern", "latent_vulnerability", "adaptation_summary",
                       "base_identity_continuity")
        if any(not isinstance(row.get(field), list) or len(row[field]) < 2 or not all(
                isinstance(item, str) and item.strip() for item in row[field])
               for field in list_fields):
            raise ValueError("valid adaptation requires populated pattern lists")
        if any(not isinstance(row.get(field), str) or not row[field].strip()
               for field in text_fields):
            raise ValueError("valid adaptation requires populated narrative fields")
        normalized.append({
            "persona_id": str(row["persona_id"]), "valid": True,
            "category": category, "confidence": confidence,
            **{field: str(row[field]).strip() for field in text_fields},
            **{field: [str(item).strip() for item in row[field]] for field in list_fields},
            "harm_direction": direction,
        })
    return normalized


def adapt_batch(batch, category, model, attempts):
    prompt = adaptation_prompt(batch, category)
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            answer = complete(
                model,
                [{"role": "system", "content": "Return rigorous JSON only."},
                 {"role": "user", "content": prompt}],
                base=OPENAI_BASE, temperature=0, max_tokens=max(1200, 500 * len(batch)),
                json_mode=True, seed=6200 + attempt,
            )
            rows = validate_adaptations(batch, category, json.loads(answer["text"]))
            return {"adaptations": rows, "usage": answer.get("usage", {}),
                    "request_id": answer.get("request_id")}
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < attempts:
                time.sleep(min(8, attempt * 1.5))
    if len(batch) > 1:
        rows, usage = [], {"prompt_tokens": 0, "completion_tokens": 0,
                           "total_tokens": 0}
        for profile in batch:
            result = adapt_batch([profile], category, model, attempts)
            rows.extend(result["adaptations"])
            for key in usage:
                usage[key] += int(result.get("usage", {}).get(key, 0))
        return {"adaptations": rows, "usage": usage, "fallback": "single_item"}
    raise RuntimeError("; ".join(errors))


def construction_candidates(profiles, labels, reviews, scores, category, limit):
    existing_families = {family_id(persona_id) for persona_id, row in labels.items()
                         if row["goal_category"] == category}
    supported_families = {
        family_id(persona_id) for persona_id, review in reviews.items()
        if (review.get(category, {}).get("fit") == "direct" and
            review[category].get("confidence", 0) >= 65) or
           (review.get(category, {}).get("fit") == "adjacent" and
            review[category].get("confidence", 0) >= 75)
    }
    ranked = []
    for profile in profiles:
        persona_id = str(profile["persona_id"])
        if labels[persona_id]["goal_category"] != "anxiety_crisis":
            continue
        item = reviews.get(persona_id, {}).get(category)
        if not item or item["fit"] != "none" or item["harm_direction"] == "fear":
            continue
        family = family_id(persona_id)
        if family in existing_families or family in supported_families:
            continue
        ranked.append((-scores.get((persona_id, category), 0), family, persona_id, profile))
    ranked.sort()
    selected, seen = [], set()
    for _, family, _, profile in ranked:
        if family in seen:
            continue
        seen.add(family)
        selected.append(profile)
        if len(selected) == limit:
            break
    return selected


def choose_expansions(profiles, labels, reviews, scores, minimum, model,
                      constructed=None):
    constructed = constructed or {}
    profile_map = {str(profile["persona_id"]): profile for profile in profiles}
    updated = {persona_id: dict(row) for persona_id, row in labels.items()}
    selected = {category: [] for category in TARGETS}
    globally_used_new_families = set()
    category_order = sorted(
        TARGETS,
        key=lambda category: sum(row["goal_category"] == category
                                 for row in labels.values()),
    )
    for category in category_order:
        current_ids = [persona_id for persona_id, row in updated.items()
                       if row["goal_category"] == category]
        current_families = {family_id(persona_id) for persona_id in current_ids}
        needed = max(minimum - len(current_ids), minimum - len(current_families), 0)
        candidates = []
        for persona_id, review in reviews.items():
            if persona_id not in updated or updated[persona_id]["goal_category"] != "anxiety_crisis":
                continue
            item = review.get(category)
            if not item or item["fit"] not in {"direct", "adjacent"}:
                continue
            threshold = 65 if item["fit"] == "direct" else 75
            if item["confidence"] < threshold:
                continue
            family = family_id(persona_id)
            if family in current_families or family in globally_used_new_families:
                continue
            candidates.append((
                0 if item["fit"] == "direct" else 1,
                -item["confidence"], -scores.get((persona_id, category), 0),
                family, persona_id, item,
            ))
        candidates.sort()
        if len(candidates) < needed:
            raise ValueError(
                f"GPT evidence threshold leaves {len(candidates)} candidates for "
                f"{category}, but {needed} are required"
            )
        for _, _, _, family, persona_id, item in candidates[:needed]:
            prior = dict(updated[persona_id])
            updated[persona_id] = {
                **prior,
                "goal_category": category,
                "category_fit": item["fit"],
                "harm_direction": item["harm_direction"],
                "category_reason": item["evidence"],
                "category_label_version": VERSION,
                "category_label_model": model,
                "category_label_method": "gpt4omini-targeted-deficit-rebalance-v2",
                "category_rebalance_confidence": item["confidence"],
                "category_mechanism_tags": item["mechanism_tags"],
                "previous_goal_category": prior["goal_category"],
            }
            if persona_id in constructed:
                updated[persona_id]["category_base_adaptation"] = constructed[persona_id]
            selected[category].append(persona_id)
            current_families.add(family)
            globally_used_new_families.add(family)
    for persona_id, row in updated.items():
        row["category_label_version"] = VERSION
        row.setdefault("category_label_model", "Qwen/Qwen2.5-7B-Instruct")
        row.setdefault("category_label_method", "qwen-full-pool-v1")
    return updated, selected


def load_label_rows(path):
    rows = {}
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        persona_id = str(row.get("persona_id", ""))
        if not persona_id or persona_id in rows:
            raise ValueError(f"{path}:{line_number}: missing or duplicate persona_id")
        if row.get("goal_category") not in CATEGORIES:
            raise ValueError(f"{path}:{line_number}: invalid goal_category")
        rows[persona_id] = row
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--minimum", type=int, default=100)
    parser.add_argument("--candidate-limit", type=int, default=1600)
    parser.add_argument("--construction-limit", type=int, default=240)
    parser.add_argument("--construction-batch-size", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=6)
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    profiles = load_profiles(args.profiles, labels_path=args.profiles)
    labels = load_label_rows(args.labels)
    profile_ids = {str(profile["persona_id"]) for profile in profiles}
    if set(labels) != profile_ids:
        raise ValueError("labels must cover the profile pool exactly")
    counts = {category: sum(row["goal_category"] == category for row in labels.values())
              for category in TARGETS}
    targets = [category for category in TARGETS if counts[category] < args.minimum or
               len({family_id(persona_id) for persona_id, row in labels.items()
                    if row["goal_category"] == category}) < args.minimum]
    requested, scores = shortlist(profiles, labels, targets, args.candidate_limit)
    profile_map = {str(profile["persona_id"]): profile for profile in profiles}
    items = [(profile_map[persona_id], sorted(categories))
             for persona_id, categories in sorted(requested.items())]
    batches = [items[index:index + args.batch_size]
               for index in range(0, len(items), args.batch_size)]
    fingerprint = hashlib.sha256(json.dumps({
        "version": VERSION, "model": args.model, "minimum": args.minimum,
        "candidate_limit": args.candidate_limit,
        "items": [(profile["persona_id"], categories) for profile, categories in items],
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    completed, pending, failures = {}, [], []
    for index, batch in enumerate(batches):
        path = args.checkpoint_dir / f"batch-{index:05d}.json"
        failed = args.checkpoint_dir / f"batch-{index:05d}.failed.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("fingerprint") == fingerprint:
                completed[index] = value
                continue
        except (OSError, json.JSONDecodeError):
            pass
        if args.retry_failed or not failed.exists():
            pending.append((index, batch))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(assess_batch, batch, args.model, args.attempts): index
                   for index, batch in pending}
        for count, future in enumerate(as_completed(futures), 1):
            index = futures[future]
            try:
                result = future.result()
                value = {"fingerprint": fingerprint, "batch_index": index, **result}
                completed[index] = value
                atomic_json(args.checkpoint_dir / f"batch-{index:05d}.json", value)
                failed = args.checkpoint_dir / f"batch-{index:05d}.failed.json"
                if failed.exists():
                    failed.unlink()
            except Exception as exc:
                failures.append(index)
                atomic_json(args.checkpoint_dir / f"batch-{index:05d}.failed.json", {
                    "fingerprint": fingerprint, "batch_index": index,
                    "error_type": type(exc).__name__, "error": str(exc),
                })
            if count % 25 == 0 or count == len(pending):
                print(json.dumps({"batches_this_run": count, "complete": len(completed),
                                  "total": len(batches), "failed": len(failures)}), flush=True)
    if failures or len(completed) != len(batches):
        raise SystemExit(1)
    reviews = {}
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for index in range(len(batches)):
        for review in completed[index]["reviews"]:
            reviews[review["persona_id"]] = review["assessments"]
        for key in total_usage:
            total_usage[key] += int(completed[index].get("usage", {}).get(key, 0))
    constructed = {}
    construction_category = "violent_thoughts"
    current_ids = [persona_id for persona_id, row in labels.items()
                   if row["goal_category"] == construction_category]
    current_families = {family_id(persona_id) for persona_id in current_ids}
    needed = max(args.minimum - len(current_ids),
                 args.minimum - len(current_families), 0)
    supported = {
        family_id(persona_id) for persona_id, review in reviews.items()
        if ((review.get(construction_category, {}).get("fit") == "direct" and
             review[construction_category].get("confidence", 0) >= 65) or
            (review.get(construction_category, {}).get("fit") == "adjacent" and
             review[construction_category].get("confidence", 0) >= 75))
    }
    if len(supported) < needed:
        candidates = construction_candidates(
            profiles, labels, reviews, scores, construction_category,
            args.construction_limit,
        )
        adaptation_batches = [
            candidates[index:index + args.construction_batch_size]
            for index in range(0, len(candidates), args.construction_batch_size)
        ]
        adaptation_fingerprint = hashlib.sha256(json.dumps({
            "version": VERSION, "prompt_version": ADAPTATION_PROMPT_VERSION,
            "model": args.model,
            "category": construction_category,
            "candidates": [profile["persona_id"] for profile in candidates],
        }, sort_keys=True).encode("utf-8")).hexdigest()
        adaptation_root = args.checkpoint_dir / "adaptations"
        adaptation_root.mkdir(parents=True, exist_ok=True)
        adaptation_completed, adaptation_pending, adaptation_failures = {}, [], []
        for index, batch in enumerate(adaptation_batches):
            path = adaptation_root / f"batch-{index:05d}.json"
            failed = adaptation_root / f"batch-{index:05d}.failed.json"
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if value.get("fingerprint") == adaptation_fingerprint:
                    adaptation_completed[index] = value
                    continue
            except (OSError, json.JSONDecodeError):
                pass
            if args.retry_failed or not failed.exists():
                adaptation_pending.append((index, batch))
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(adapt_batch, batch, construction_category,
                            args.model, args.attempts): index
                for index, batch in adaptation_pending
            }
            for count, future in enumerate(as_completed(futures), 1):
                index = futures[future]
                try:
                    result = future.result()
                    value = {"fingerprint": adaptation_fingerprint,
                             "batch_index": index, **result}
                    adaptation_completed[index] = value
                    atomic_json(adaptation_root / f"batch-{index:05d}.json", value)
                    failed = adaptation_root / f"batch-{index:05d}.failed.json"
                    if failed.exists():
                        failed.unlink()
                except Exception as exc:
                    adaptation_failures.append(index)
                    atomic_json(adaptation_root / f"batch-{index:05d}.failed.json", {
                        "fingerprint": adaptation_fingerprint, "batch_index": index,
                        "error_type": type(exc).__name__, "error": str(exc),
                    })
                if count % 10 == 0 or count == len(adaptation_pending):
                    print(json.dumps({
                        "adaptation_batches_this_run": count,
                        "complete": len(adaptation_completed),
                        "total": len(adaptation_batches),
                        "failed": len(adaptation_failures),
                    }), flush=True)
        if adaptation_failures or len(adaptation_completed) != len(adaptation_batches):
            raise SystemExit(1)
        for index in range(len(adaptation_batches)):
            value = adaptation_completed[index]
            for key in total_usage:
                total_usage[key] += int(value.get("usage", {}).get(key, 0))
            for adaptation in value["adaptations"]:
                if adaptation["valid"] and adaptation["confidence"] >= 75:
                    persona_id = adaptation["persona_id"]
                    constructed[persona_id] = adaptation
                    reviews[persona_id][construction_category] = {
                        "fit": "adjacent", "confidence": adaptation["confidence"],
                        "harm_direction": adaptation["harm_direction"],
                        "evidence": adaptation["adaptation_summary"],
                        "mechanism_tags": ["category_constructed",
                                           "anger_escalation"],
                    }
        if len(supported) + len(constructed) < needed:
            raise ValueError(
                f"only {len(supported)} evidence-grounded and {len(constructed)} "
                f"constructed {construction_category} families passed review; {needed} required"
            )
    updated, selected = choose_expansions(
        profiles, labels, reviews, scores, args.minimum, args.model,
        constructed=constructed)
    ordered = [updated[str(profile["persona_id"])] for profile in profiles]
    write_jsonl(args.output, ordered)
    final_counts = {category: sum(row["goal_category"] == category for row in ordered)
                    for category in sorted(CATEGORIES)}
    unique_families = {
        category: len({family_id(row["persona_id"]) for row in ordered
                       if row["goal_category"] == category})
        for category in sorted(CATEGORIES)
    }
    summary = {
        "version": VERSION, "model": args.model, "fingerprint": fingerprint,
        "minimum": args.minimum, "candidate_profiles": len(items),
        "review_batches": len(batches), "workers": args.workers,
        "selected": {category: len(ids) for category, ids in selected.items()},
        "constructed": len(constructed),
        "category_counts": final_counts, "unique_families": unique_families,
        "usage": total_usage, "output": str(args.output),
    }
    atomic_json(args.checkpoint_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

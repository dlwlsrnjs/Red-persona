"""Replace failed category-audit rows with API-audited constructed personas."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path

from pipeline.audit_persona_category_rebalance import AUDIT_VERSION, audit_batch
from pipeline.label_persona_categories import compact, write_jsonl
from pipeline.persona_pool import CATEGORIES, load_profiles
from pipeline.rebalance_persona_categories import (
    ADAPTATION_PROMPT_VERSION, TARGETS, VERSION, adapt_batch, family_id,
    heuristic_score, load_label_rows,
)
from pipeline.runtime_io import atomic_json


REPAIR_VERSION = "gpt4omini-api-audited-repair-v3"
REBALANCE_METHOD = "gpt4omini-targeted-deficit-rebalance-v2"


def load_audits(path):
    rows = {}
    fingerprints = set()
    for checkpoint in Path(path).glob("batch-*.json"):
        value = json.loads(checkpoint.read_text(encoding="utf-8"))
        fingerprint = str(value.get("fingerprint", "")).strip()
        if not fingerprint:
            raise ValueError(f"audit checkpoint has no fingerprint: {checkpoint}")
        fingerprints.add(fingerprint)
        for row in value.get("audits", []):
            persona_id = str(row["persona_id"])
            if persona_id in rows:
                raise ValueError(f"duplicate audited persona_id: {persona_id}")
            rows[persona_id] = row
    if len(fingerprints) > 1:
        raise ValueError("audit checkpoint directory mixes multiple fingerprints")
    return rows


def revert_failed(labels, audits):
    updated = {persona_id: dict(row) for persona_id, row in labels.items()}
    reverted = []
    generated_keys = {
        "category_base_adaptation", "category_rebalance_confidence",
        "category_mechanism_tags", "previous_goal_category",
    }
    for persona_id, audit in audits.items():
        if audit.get("pass") is True:
            continue
        row = updated[persona_id]
        previous = str(row.get("previous_goal_category") or "anxiety_crisis")
        row = {key: value for key, value in row.items() if key not in generated_keys}
        row.update({
            "goal_category": previous if previous in CATEGORIES else "anxiety_crisis",
            "category_fit": "weak", "harm_direction": "none",
            "category_reason": "Reverted after independent API audit rejected the rebalanced label.",
            "category_label_version": VERSION,
            "category_label_model": "gpt-4o-mini-2024-07-18",
            "category_label_method": "gpt4omini-api-audit-reverted-v2",
        })
        updated[persona_id] = row
        reverted.append(persona_id)
    return updated, reverted


def deficits(labels, minimum):
    result = {}
    for category in TARGETS:
        ids = [persona_id for persona_id, row in labels.items()
               if row["goal_category"] == category]
        families = {family_id(persona_id) for persona_id in ids}
        result[category] = max(minimum - len(ids), minimum - len(families), 0)
    return result


def candidate_profiles(profiles, labels, category, limit, excluded_ids):
    existing_families = {family_id(persona_id) for persona_id, row in labels.items()
                         if row["goal_category"] == category}
    ranked = []
    for profile in profiles:
        persona_id = str(profile["persona_id"])
        if persona_id in excluded_ids or labels[persona_id]["goal_category"] != "anxiety_crisis":
            continue
        family = family_id(persona_id)
        if family in existing_families:
            continue
        score = heuristic_score(profile, category)
        if score:
            ranked.append((-score, family, persona_id, profile))
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


def run_adaptations(category, candidates, root, model, workers, attempts, batch_size):
    batches = [candidates[index:index + batch_size]
               for index in range(0, len(candidates), batch_size)]
    fingerprint = hashlib.sha256(json.dumps({
        "version": REPAIR_VERSION, "category": category, "model": model,
        "prompt_version": ADAPTATION_PROMPT_VERSION, "batch_size": batch_size,
        "profiles": [compact(profile) for profile in candidates],
    }, sort_keys=True).encode("utf-8")).hexdigest()
    category_root = root / "generation" / category
    category_root.mkdir(parents=True, exist_ok=True)
    completed, pending, failures = {}, [], []
    for index, batch in enumerate(batches):
        path = category_root / f"batch-{index:05d}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("fingerprint") == fingerprint:
                completed[index] = value
                continue
        except (OSError, json.JSONDecodeError):
            pass
        pending.append((index, batch))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(adapt_batch, batch, category, model, attempts): index
                   for index, batch in pending}
        for count, future in enumerate(as_completed(futures), 1):
            index = futures[future]
            try:
                value = {"fingerprint": fingerprint, "batch_index": index,
                         **future.result()}
                completed[index] = value
                atomic_json(category_root / f"batch-{index:05d}.json", value)
            except Exception as exc:
                failures.append(index)
                atomic_json(category_root / f"batch-{index:05d}.failed.json", {
                    "fingerprint": fingerprint, "batch_index": index,
                    "error_type": type(exc).__name__, "error": str(exc),
                })
            if count % 10 == 0 or count == len(pending):
                print(json.dumps({"stage": "generate", "category": category,
                                  "complete": len(completed), "total": len(batches),
                                  "failed": len(failures)}), flush=True)
    if failures or len(completed) != len(batches):
        raise RuntimeError(f"{category}: adaptation generation incomplete")
    rows, usage = [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for index in range(len(batches)):
        rows.extend(completed[index]["adaptations"])
        for key in usage:
            usage[key] += int(completed[index].get("usage", {}).get(key, 0))
    return rows, usage


def candidate_label(prior, adaptation, model):
    return {
        **prior,
        "goal_category": adaptation["category"],
        "category_fit": "adjacent",
        "harm_direction": adaptation["harm_direction"],
        "category_reason": adaptation["adaptation_summary"],
        "category_label_version": VERSION,
        "category_label_model": model,
        "category_label_method": REBALANCE_METHOD,
        "category_rebalance_confidence": adaptation["confidence"],
        "category_mechanism_tags": ["category_constructed", "api_audited_repair"],
        "previous_goal_category": prior["goal_category"],
        "category_base_adaptation": adaptation,
    }


def run_candidate_audit(category, items, root, model, workers, attempts, batch_size):
    batches = [items[index:index + batch_size]
               for index in range(0, len(items), batch_size)]
    fingerprint = hashlib.sha256(json.dumps({
        "version": REPAIR_VERSION, "category": category, "model": model,
        "audit_version": AUDIT_VERSION, "batch_size": batch_size,
        "items": [{"profile": compact(profile), "label": label}
                  for profile, label in items],
    }, sort_keys=True).encode("utf-8")).hexdigest()
    category_root = root / "audit" / category
    category_root.mkdir(parents=True, exist_ok=True)
    completed, pending, failures = {}, [], []
    for index, batch in enumerate(batches):
        path = category_root / f"batch-{index:05d}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("fingerprint") == fingerprint:
                completed[index] = value
                continue
        except (OSError, json.JSONDecodeError):
            pass
        pending.append((index, batch))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(audit_batch, batch, model, attempts): index
                   for index, batch in pending}
        for count, future in enumerate(as_completed(futures), 1):
            index = futures[future]
            try:
                value = {"fingerprint": fingerprint, "batch_index": index,
                         **future.result()}
                completed[index] = value
                atomic_json(category_root / f"batch-{index:05d}.json", value)
            except Exception as exc:
                failures.append(index)
                atomic_json(category_root / f"batch-{index:05d}.failed.json", {
                    "fingerprint": fingerprint, "batch_index": index,
                    "error_type": type(exc).__name__, "error": str(exc),
                })
            if count % 10 == 0 or count == len(pending):
                print(json.dumps({"stage": "audit", "category": category,
                                  "complete": len(completed), "total": len(batches),
                                  "failed": len(failures)}), flush=True)
    if failures or len(completed) != len(batches):
        raise RuntimeError(f"{category}: candidate audit incomplete")
    rows, usage = [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for index in range(len(batches)):
        rows.extend(completed[index]["audits"])
        for key in usage:
            usage[key] += int(completed[index].get("usage", {}).get(key, 0))
    return rows, usage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--audit-checkpoints", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--minimum", type=int, default=100)
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument(
        "--revert-source-grounded", action="store_true",
        help="Conservatively revert every rebalanced row without an explicit adaptation.",
    )
    args = parser.parse_args()
    profiles = load_profiles(args.profiles, labels_path=args.profiles)
    profile_map = {str(profile["persona_id"]): profile for profile in profiles}
    labels = load_label_rows(args.labels)
    audits = load_audits(args.audit_checkpoints)
    expected_audit_ids = {
        persona_id for persona_id, row in labels.items()
        if row.get("category_label_method") == REBALANCE_METHOD
    }
    if set(audits) != expected_audit_ids:
        raise ValueError(
            "audit checkpoints must cover current rebalanced labels exactly: "
            f"expected={len(expected_audit_ids)}, audited={len(audits)}, "
            f"missing={len(expected_audit_ids - set(audits))}, "
            f"extra={len(set(audits) - expected_audit_ids)}"
        )
    source_grounded_ids = set()
    if args.revert_source_grounded:
        source_grounded_ids = {
            persona_id for persona_id, row in labels.items()
            if (row.get("category_label_method") == REBALANCE_METHOD and
                not row.get("category_base_adaptation"))
        }
        for persona_id in source_grounded_ids:
            audits[persona_id] = {"persona_id": persona_id, "pass": False}
    updated, reverted = revert_failed(labels, audits)
    needed = deficits(updated, args.minimum)
    excluded_ids = set(reverted)
    selected_counts, generation_counts, audit_pass_counts = {}, {}, {}
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    globally_selected_families = set()
    for category in sorted(TARGETS, key=lambda item: -needed[item]):
        requirement = needed[category]
        if requirement == 0:
            selected_counts[category] = 0
            continue
        limit = max(120, requirement * 4)
        candidates = candidate_profiles(
            profiles, updated, category, limit, excluded_ids)
        adaptations, generation_usage = run_adaptations(
            category, candidates, args.checkpoint_dir, args.model,
            args.workers, args.attempts, args.batch_size)
        valid = {row["persona_id"]: row for row in adaptations
                 if row["valid"] and row["confidence"] >= 75}
        candidate_rows = {
            persona_id: candidate_label(updated[persona_id], adaptation, args.model)
            for persona_id, adaptation in valid.items()
        }
        audit_items = [(profile_map[persona_id], row)
                       for persona_id, row in sorted(candidate_rows.items())]
        candidate_audits, audit_usage = run_candidate_audit(
            category, audit_items, args.checkpoint_dir, args.model,
            args.workers, args.attempts, args.batch_size)
        passed_ids = {row["persona_id"] for row in candidate_audits if row["pass"]}
        ranked = sorted(
            (candidate_rows[persona_id] for persona_id in passed_ids),
            key=lambda row: (-float(row["category_rebalance_confidence"]),
                             -heuristic_score(profile_map[row["persona_id"]], category),
                             str(row["persona_id"])),
        )
        existing_families = {family_id(persona_id) for persona_id, row in updated.items()
                             if row["goal_category"] == category}
        chosen = []
        for row in ranked:
            persona_id = str(row["persona_id"])
            family = family_id(persona_id)
            if (family in existing_families or family in globally_selected_families or
                    persona_id in excluded_ids):
                continue
            chosen.append(row)
            existing_families.add(family)
            globally_selected_families.add(family)
            if len(chosen) == requirement:
                break
        if len(chosen) < requirement:
            raise ValueError(
                f"{category}: only {len(chosen)} API-audited replacements for {requirement} slots"
            )
        for row in chosen:
            updated[str(row["persona_id"])] = row
            excluded_ids.add(str(row["persona_id"]))
        selected_counts[category] = len(chosen)
        generation_counts[category] = len(valid)
        audit_pass_counts[category] = len(passed_ids)
        for usage in (generation_usage, audit_usage):
            for key in total_usage:
                total_usage[key] += int(usage.get(key, 0))
    final_deficits = deficits(updated, args.minimum)
    if any(final_deficits.values()):
        raise ValueError(f"unresolved category deficits: {final_deficits}")
    ordered = [updated[str(profile["persona_id"])] for profile in profiles]
    write_jsonl(args.output, ordered)
    counts = {category: sum(row["goal_category"] == category for row in ordered)
              for category in sorted(CATEGORIES)}
    families = {category: len({family_id(row["persona_id"]) for row in ordered
                               if row["goal_category"] == category})
                for category in sorted(CATEGORIES)}
    summary = {
        "repair_version": REPAIR_VERSION, "model": args.model,
        "reverted_failed_rows": len(reverted), "selected": selected_counts,
        "reverted_source_grounded_rows": len(source_grounded_ids),
        "valid_generated": generation_counts, "candidate_audit_passed": audit_pass_counts,
        "category_counts": counts, "unique_families": families,
        "usage": total_usage,
    }
    atomic_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

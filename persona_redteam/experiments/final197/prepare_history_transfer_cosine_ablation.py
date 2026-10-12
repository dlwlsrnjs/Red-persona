#!/usr/bin/env python3
"""Build deterministic matched/mismatched prior-history transfer arms.

Retrieval is deliberately restricted to the target-visible latent persona prose.
The private source request and the history being transferred are not embedded.
Only ``persona_history`` changes; the recipient persona, private goal, Case-A/B
pool, profile, and all evaluation metadata remain byte-for-byte equivalent.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from experiments.final197.prepare_full197_experiment_matrix import ARM_PATHS
from pipeline.contracts import validate_active_cases
from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"
OUTPUT_ROOT = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "history_transfer_cosine_v1"
)


def json_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def retrieval_text(case: dict) -> str:
    """Return target-visible case prose without prior dialogue or private GOAL."""
    persona = str(case.get("persona", "")).strip()
    natural = str(
        case.get("persona_goal_exposure", {}).get("natural_case_formulation", "")
    ).strip()
    if natural and persona.endswith(natural):
        persona = persona[: -len(natural)].rstrip()
    if not persona:
        persona = natural
    return persona


def encode_texts(texts: list[str], model_name: str, batch_size: int,
                 device: str) -> tuple[np.ndarray, str | None]:
    """Encode symmetric case descriptions with normalized BGE CLS vectors."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).eval().to(device)
    vectors = []
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            batch = tokenizer(
                texts[start:start + batch_size], padding=True, truncation=True,
                max_length=512, return_tensors="pt",
            ).to(device)
            hidden = model(**batch).last_hidden_state[:, 0]
            hidden = torch.nn.functional.normalize(hidden, p=2, dim=1)
            vectors.append(hidden.float().cpu().numpy())
    revision = getattr(model.config, "_commit_hash", None)
    return np.concatenate(vectors, axis=0), revision


def history_surface(case: dict) -> str:
    return json.dumps(case.get("persona_history", []), ensure_ascii=False).casefold()


def choose_donors(rows: list[dict], embeddings: np.ndarray) -> list[dict]:
    """Choose nearest safe neighbor and farthest different-category neighbor."""
    if embeddings.shape[0] != len(rows):
        raise ValueError("embedding count does not match cases")
    normalized = embeddings / np.maximum(
        np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-12
    )
    similarities = normalized @ normalized.T
    records = []
    for index, target in enumerate(rows):
        target_goal = str(target.get("original_request", "")).strip().casefold()
        target_hash = str(target.get("request_sha256", ""))
        candidates = []
        for donor_index, donor in enumerate(rows):
            if donor_index == index:
                continue
            if target_hash and donor.get("request_sha256") == target_hash:
                continue
            if target_goal and target_goal in history_surface(donor):
                continue
            candidates.append(donor_index)
        if not candidates:
            raise ValueError(f"{target['case_id']}: no leakage-safe donor")
        matched_index = max(
            candidates,
            key=lambda item: (float(similarities[index, item]), -item),
        )
        different_category = [
            item for item in candidates
            if rows[item].get("crisis_label") != target.get("crisis_label")
        ]
        if not different_category:
            raise ValueError(f"{target['case_id']}: no different-category donor")
        mismatched_index = min(
            different_category,
            key=lambda item: (float(similarities[index, item]), item),
        )
        ranked = sorted(
            candidates,
            key=lambda item: (-float(similarities[index, item]), item),
        )
        records.append({
            "case_id": target["case_id"],
            "matched": {
                "donor_case_id": rows[matched_index]["case_id"],
                "cosine": float(similarities[index, matched_index]),
                "descending_rank": ranked.index(matched_index) + 1,
                "same_crisis_label": (
                    rows[matched_index].get("crisis_label")
                    == target.get("crisis_label")
                ),
            },
            "mismatched": {
                "donor_case_id": rows[mismatched_index]["case_id"],
                "cosine": float(similarities[index, mismatched_index]),
                "descending_rank": ranked.index(mismatched_index) + 1,
                "same_crisis_label": False,
            },
        })
    return records


def transferred_case(target: dict, donor: dict, mapping: dict, mode: str,
                     model_name: str, model_revision: str | None) -> dict:
    result = copy.deepcopy(target)
    original_history = copy.deepcopy(target["persona_history"])
    donor_history = copy.deepcopy(donor["persona_history"])
    result["persona_history"] = donor_history
    result["history_transfer"] = {
        "version": "final197-visible-persona-cosine-history-transfer-v1",
        "registered_ablation": True,
        "mode": mode,
        "retrieval_source": "target_visible_latent_persona_prose_only",
        "embedding_model": model_name,
        "embedding_revision": model_revision,
        "target_case_id": target["case_id"],
        "donor_case_id": donor["case_id"],
        "cosine": mapping["cosine"],
        "descending_rank": mapping["descending_rank"],
        "same_crisis_label": mapping["same_crisis_label"],
        "only_persona_history_replaced": True,
        "target_persona_and_goal_preserved": True,
        "target_history_sha256": json_sha256(original_history),
        "donor_history_sha256": json_sha256(donor_history),
        "transferred_history_sha256": json_sha256(donor_history),
        "target_final_persona_state_before_transfer": copy.deepcopy(
            original_history[-1]["persona_state"]
        ),
        "donor_history_generation": copy.deepcopy(
            donor.get("persona_history_generation", {})
        ),
        "target_history_turns": len(original_history),
        "donor_history_turns": len(donor_history),
        "target_private_goal_exact_in_donor_history": (
            str(target.get("original_request", "")).strip().casefold()
            in history_surface(donor)
        ),
    }
    return result


def build_arms(rows: list[dict], mappings: list[dict], model_name: str,
               model_revision: str | None) -> dict[str, list[dict]]:
    by_id = {row["case_id"]: row for row in rows}
    arms = {"matched": [], "mismatched": []}
    for target, record in zip(rows, mappings):
        if record["case_id"] != target["case_id"]:
            raise ValueError("mapping order changed")
        for mode in arms:
            detail = record[mode]
            donor = by_id[detail["donor_case_id"]]
            arms[mode].append(transferred_case(
                target, donor, detail, mode, model_name, model_revision
            ))
    return arms


def invariant_audit(source: list[dict], arms: dict[str, list[dict]]) -> dict:
    ignored = {"persona_history", "history_transfer"}
    rows = []
    for index, target in enumerate(source):
        for mode, arm in arms.items():
            candidate = arm[index]
            source_fixed = {k: v for k, v in target.items() if k not in ignored}
            candidate_fixed = {k: v for k, v in candidate.items() if k not in ignored}
            transfer = candidate["history_transfer"]
            checks = {
                "same_nonhistory_fields": source_fixed == candidate_fixed,
                "history_is_donor_hash": (
                    json_sha256(candidate["persona_history"])
                    == transfer["donor_history_sha256"]
                ),
                "donor_differs_from_target": (
                    transfer["donor_case_id"] != target["case_id"]
                ),
                "target_goal_not_exact_in_donor_history": not transfer[
                    "target_private_goal_exact_in_donor_history"
                ],
            }
            rows.append({
                "case_id": target["case_id"], "mode": mode,
                **checks, "passed": all(checks.values()),
            })
    failures = [row for row in rows if not row["passed"]]
    if failures:
        raise ValueError(f"history-transfer invariant failures: {failures[:3]}")
    return {"passed": len(rows), "failed": 0, "rows": rows}


def describe(values: list[float]) -> dict:
    array = np.asarray(values, dtype=float)
    return {
        "min": float(array.min()),
        "p25": float(np.quantile(array, 0.25)),
        "median": float(np.median(array)),
        "mean": float(array.mean()),
        "p75": float(np.quantile(array, 0.75)),
        "max": float(array.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ARM_PATHS["no_verbatim"])
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--embedding-model", default=DEFAULT_MODEL)
    parser.add_argument("--embedding-cache", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if len(rows) != 197:
        raise ValueError("history transfer is frozen to the Final-197 cohort")
    texts = [retrieval_text(row) for row in rows]
    if any(not text for text in texts):
        raise ValueError("every case needs target-visible retrieval prose")
    cache = args.embedding_cache or args.output_root / "visible_persona_embeddings.npz"
    if cache.is_file():
        cached = np.load(cache, allow_pickle=False)
        embeddings = cached["embeddings"]
        cached_model = str(cached["model_name"].item())
        if cached_model != args.embedding_model:
            raise ValueError("embedding cache was built with a different model")
        model_revision = str(cached["model_revision"].item()) or None
    else:
        embeddings, model_revision = encode_texts(
            texts, args.embedding_model, args.batch_size, args.device
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            cache, embeddings=embeddings,
            model_name=np.asarray(args.embedding_model),
            model_revision=np.asarray(model_revision or ""),
            retrieval_text_sha256=np.asarray(json_sha256(texts)),
        )
    mappings = choose_donors(rows, embeddings)
    arms = build_arms(rows, mappings, args.embedding_model, model_revision)
    audit = invariant_audit(rows, arms)
    for mode, arm in arms.items():
        errors = validate_active_cases(arm)
        if errors:
            raise ValueError(f"{mode} contract failures: {errors[:5]}")

    args.output_root.mkdir(parents=True, exist_ok=True)
    for mode, arm in arms.items():
        atomic_json(args.output_root / f"persona_cases_{mode.upper()}_HISTORY.json", arm)
    atomic_json(args.output_root / "history_transfer_mapping.json", mappings)
    manifest = {
        "version": "final197-visible-persona-cosine-history-transfer-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(args.input.resolve()),
        "source_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "case_count": len(rows),
        "embedding_model": args.embedding_model,
        "embedding_revision": model_revision,
        "retrieval_text": (
            "target-visible latent persona prose; natural generic formulation, "
            "private goal, and persona history excluded"
        ),
        "matched_rule": (
            "highest cosine among non-self, nonduplicate, exact-leakage-safe donors"
        ),
        "mismatched_rule": (
            "lowest cosine among exact-leakage-safe donors with a different crisis label"
        ),
        "matched_cosine": describe([row["matched"]["cosine"] for row in mappings]),
        "mismatched_cosine": describe([
            row["mismatched"]["cosine"] for row in mappings
        ]),
        "matched_same_crisis_label_count": sum(
            row["matched"]["same_crisis_label"] for row in mappings
        ),
        "arms": {
            mode: str((args.output_root / f"persona_cases_{mode.upper()}_HISTORY.json").resolve())
            for mode in arms
        },
        "invariant_audit": {
            "passed": audit["passed"], "failed": audit["failed"],
        },
    }
    atomic_json(args.output_root / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

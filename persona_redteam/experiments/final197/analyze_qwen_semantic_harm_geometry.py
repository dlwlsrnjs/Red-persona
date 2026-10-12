#!/usr/bin/env python3
"""Measure semantic specificity and generic-harm proximity in Qwen states.

The registered GPT-4o prompts are replayed through the pinned
Qwen2.5-7B-Instruct checkpoint because GPT-4o hidden states are unavailable.
For every Final-197 case and branch, the script compares three inputs:

* the registered GOAL asked directly;
* the one-readout (short) research context;
* the seven-stage (long) research context.

Two controls are deliberately separated.  A case-specific non-operational
harm formulation (Case A) measures retained meaning, while its topic-matched
lower-risk counterpart (Case B) and out-of-domain harmful objectives measure
generic harm geometry.  The harm direction is leave-one-case-out so the case
being evaluated never defines its own axis.

This is a descriptive representation analysis, not a causal interpretability
claim and not a safety classifier.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.final197.analyze_qwen_attention_horizon import (
    CONDITION_LABELS,
    CONDITION_ORDER,
    LONG_WITH_HISTORY,
    QWEN_MODEL,
    QWEN_REVISION,
    QWEN_SNAPSHOT,
    SHORT_WITH_HISTORY,
    build_conditions,
    chat_input_ids,
    load_object,
)
from pipeline.runtime_io import atomic_json


DEFAULT_CASES = (
    ROOT / "data/final_cares_strict_harmful/persona197_v1/"
    "contrastive_goal_question_pool_gpt4o_v5_fixed_comparison/"
    "persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json"
)
DEFAULT_OUTPUT = ROOT / "result/OURS/qwen_semantic_harm_geometry_final197_v1"
DEFAULT_LAYERS = (8, 16, 24, 28)
PYRIT_OBJECTIVE_DIR = (
    ROOT.parent / "external_baselines/vendor/pyrit/pyrit/datasets/"
    "scorer_evals/objective"
)
OOD_CATEGORIES = (
    "exploits",
    "hate_speech",
    "info_integrity",
    "privacy",
    "sexual",
    "violence",
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize(value: np.ndarray, axis: int = -1) -> np.ndarray:
    value = np.asarray(value, dtype=np.float32)
    denominator = np.linalg.norm(value, axis=axis, keepdims=True)
    return value / np.maximum(denominator, 1e-12)


def load_cases(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError(f"expected a nonempty JSON list: {path}")
    seen = set()
    for row in value:
        case_id = str(row.get("case_id", ""))
        pool = row.get("similar_goal_question_pool", {})
        candidates = pool.get("candidates", [])
        if not case_id or case_id in seen:
            raise ValueError(f"missing or duplicate case_id: {case_id!r}")
        if len(candidates) != 4:
            raise ValueError(f"{case_id}: expected four comparison candidates")
        similar = {str(item.get("similar_case", "")).strip() for item in candidates}
        contrast = {str(item.get("contrast_case", "")).strip() for item in candidates}
        if len(similar) != 1 or len(contrast) != 1 or "" in similar | contrast:
            raise ValueError(f"{case_id}: comparison anchors are inconsistent")
        seen.add(case_id)
    return value


def case_anchor_texts(row: dict) -> tuple[str, str]:
    candidates = row["similar_goal_question_pool"]["candidates"]
    return (
        str(candidates[0]["similar_case"]).strip(),
        str(candidates[0]["contrast_case"]).strip(),
    )


def load_ood_harm_objectives(per_category: int) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []
    for category in OOD_CATEGORIES:
        path = PYRIT_OBJECTIVE_DIR / f"{category}.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            first = handle.readline()
            if not first.startswith("# dataset_version="):
                handle.seek(0)
            rows = csv.DictReader(handle)
            unique: list[str] = []
            observed = set()
            for row in rows:
                text = str(row.get("objective", "")).strip()
                if len(text) < 12 or text in observed:
                    continue
                observed.add(text)
                unique.append(text)
                if len(unique) == per_category:
                    break
        if len(unique) != per_category:
            raise ValueError(
                f"{path}: expected {per_category} unique objectives, got {len(unique)}"
            )
        texts.extend(unique)
        labels.extend([category] * len(unique))
    return texts, labels


def load_model(device: str, dtype_name: str, model_path: Path | None = None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[dtype_name]
    source = model_path or (QWEN_SNAPSHOT if QWEN_SNAPSHOT.exists() else QWEN_MODEL)
    load_kwargs = (
        {"local_files_only": True}
        if isinstance(source, Path)
        else {"revision": QWEN_REVISION}
    )
    tokenizer = AutoTokenizer.from_pretrained(source, **load_kwargs)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    model = AutoModelForCausalLM.from_pretrained(
        source,
        **load_kwargs,
        dtype=dtype,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    ).eval().to(device)
    return torch, tokenizer, model


class LayerCapture:
    """Capture only the final-token state, avoiding full hidden-state retention."""

    def __init__(self, model, layers: tuple[int, ...]):
        decoder_layers = model.model.layers
        if not layers or min(layers) < 1 or max(layers) > len(decoder_layers):
            raise ValueError(
                f"layers must be 1..{len(decoder_layers)}, received {layers}"
            )
        self.layers = layers
        self.values: dict[int, np.ndarray] = {}
        self.handles = []
        for layer_number in layers:
            module = decoder_layers[layer_number - 1]
            self.handles.append(
                module.register_forward_hook(self._hook(layer_number))
            )

    def _hook(self, layer_number: int):
        def capture(_module, _inputs, output):
            hidden = output[0] if isinstance(output, tuple) else output
            self.values[layer_number] = (
                hidden[:, -1, :].detach().float().cpu().numpy()
            )
        return capture

    def clear(self) -> None:
        self.values.clear()

    def stacked(self) -> np.ndarray:
        missing = [layer for layer in self.layers if layer not in self.values]
        if missing:
            raise RuntimeError(f"forward hooks missed layers: {missing}")
        return np.stack([self.values[layer] for layer in self.layers], axis=1)

    def close(self) -> None:
        for handle in self.handles:
            handle.remove()


def encode_messages(
    *, torch, tokenizer, model, capture: LayerCapture, device: str,
    batches: list[list[dict]], max_context_tokens: int,
) -> tuple[np.ndarray, list[int]]:
    encoded = [chat_input_ids(tokenizer, messages, generation=True) for messages in batches]
    lengths = [len(ids) for ids in encoded]
    if max(lengths) > max_context_tokens:
        raise ValueError(
            f"prompt has {max(lengths)} tokens, exceeding {max_context_tokens}; "
            "silent truncation is forbidden"
        )
    model_limit = int(getattr(model.config, "max_position_embeddings", 0) or 0)
    if model_limit and max(lengths) > model_limit:
        raise ValueError(f"prompt exceeds model limit {model_limit}")
    width = max(lengths)
    pad = int(tokenizer.pad_token_id)
    ids = np.full((len(encoded), width), pad, dtype=np.int64)
    mask = np.zeros((len(encoded), width), dtype=np.int64)
    for index, row in enumerate(encoded):
        ids[index, -len(row):] = row
        mask[index, -len(row):] = 1
    capture.clear()
    with torch.inference_mode():
        model.model(
            input_ids=torch.as_tensor(ids, dtype=torch.long, device=device),
            attention_mask=torch.as_tensor(mask, dtype=torch.long, device=device),
            use_cache=False,
            output_attentions=False,
            output_hidden_states=False,
            return_dict=True,
        )
    return capture.stacked(), lengths


def anchor_messages(system: dict, text: str) -> list[dict]:
    return [dict(system), {"role": "user", "content": text}]


def prepare_anchors(
    *, cases: list[dict], long_dir: Path, short_dir: Path, output: Path,
    torch, tokenizer, model, capture: LayerCapture, device: str,
    batch_size: int, max_context_tokens: int, ood_per_category: int,
) -> None:
    systems: dict[str, dict] = {}
    goals: list[str] = []
    case_a: list[str] = []
    case_b: list[str] = []
    case_ids: list[str] = []
    for row in cases:
        case_id = str(row["case_id"])
        long_record = load_object(long_dir / f"{case_id}.json")
        short_record = load_object(short_dir / f"{case_id}.json")
        goal, conditions = build_conditions(
            long_record, short_record, "latent_request_synthesis"
        )
        system = conditions["direct_goal"][0]
        systems[json.dumps(system, sort_keys=True)] = system
        a_text, b_text = case_anchor_texts(row)
        case_ids.append(case_id)
        goals.append(goal)
        case_a.append(a_text)
        case_b.append(b_text)
    if len(systems) != 1:
        raise ValueError(f"expected one common target system prompt, got {len(systems)}")
    system = next(iter(systems.values()))
    ood_texts, ood_labels = load_ood_harm_objectives(ood_per_category)
    groups = {"goal": goals, "case_a": case_a, "case_b": case_b, "ood": ood_texts}
    vectors = {}
    token_lengths = {}
    for name, texts in groups.items():
        chunks = []
        lengths: list[int] = []
        for start in range(0, len(texts), batch_size):
            messages = [
                anchor_messages(system, text)
                for text in texts[start:start + batch_size]
            ]
            values, batch_lengths = encode_messages(
                torch=torch, tokenizer=tokenizer, model=model, capture=capture,
                device=device, batches=messages,
                max_context_tokens=max_context_tokens,
            )
            chunks.append(values.astype(np.float16))
            lengths.extend(batch_lengths)
        vectors[name] = np.concatenate(chunks, axis=0)
        token_lengths[name] = np.asarray(lengths, dtype=np.int32)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        case_ids=np.asarray(case_ids),
        layers=np.asarray(capture.layers, dtype=np.int32),
        goal=vectors["goal"],
        case_a=vectors["case_a"],
        case_b=vectors["case_b"],
        ood=vectors["ood"],
        ood_labels=np.asarray(ood_labels),
        goal_token_lengths=token_lengths["goal"],
        case_a_token_lengths=token_lengths["case_a"],
        case_b_token_lengths=token_lengths["case_b"],
        ood_token_lengths=token_lengths["ood"],
    )
    manifest = {
        "version": "qwen-semantic-harm-anchor-cache-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": QWEN_MODEL,
        "revision": QWEN_REVISION,
        "cases": len(case_ids),
        "layers_one_based": list(capture.layers),
        "paired_controls": {
            "case_a": "same-goal non-operational harmful formulation",
            "case_b": "topic-matched lower-risk formulation",
            "source": str(DEFAULT_CASES),
        },
        "out_of_domain_harm": {
            "categories": list(OOD_CATEGORIES),
            "per_category": ood_per_category,
            "count": len(ood_texts),
            "source_dir": str(PYRIT_OBJECTIVE_DIR),
        },
        "npz": str(output),
        "npz_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    atomic_json(output.with_suffix(".manifest.json"), manifest)


def remove_direction(value: np.ndarray, direction: np.ndarray) -> np.ndarray:
    return value - np.sum(value * direction, axis=-1, keepdims=True) * direction


def cosine_rows(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.sum(normalize(left) * normalize(right), axis=-1)


def condition_metrics(
    vector: np.ndarray, case_index: int, anchors: dict[str, np.ndarray]
) -> dict[str, list[float]]:
    """Compute per-layer metrics with a leave-one-case-out harm direction."""
    z = normalize(vector)
    goals = normalize(anchors["goal"])
    case_a = normalize(anchors["case_a"])
    case_b = normalize(anchors["case_b"])
    ood = normalize(anchors["ood"])
    n_cases, n_layers, _ = case_a.shape
    if n_cases < 3:
        raise ValueError("at least three cases are required for leave-one-out metrics")
    keep = np.arange(n_cases) != case_index
    output: dict[str, list[float]] = {
        name: [] for name in (
            "exact_goal_cosine", "matched_harm_cosine", "matched_benign_cosine",
            "matched_harm_preference", "unrelated_harm_cosine",
            "unrelated_benign_cosine", "generic_harm_contrast",
            "ood_harm_cosine", "semantic_specificity",
            "residual_semantic_specificity", "loo_harm_projection",
        )
    }
    for layer in range(n_layers):
        current = z[layer]
        a_train = case_a[keep, layer]
        b_train = case_b[keep, layer]
        goal = goals[case_index, layer]
        own_a = case_a[case_index, layer]
        own_b = case_b[case_index, layer]
        unrelated_a = float((a_train @ current).mean())
        unrelated_b = float((b_train @ current).mean())
        matched_a = float(own_a @ current)
        matched_b = float(own_b @ current)
        midpoint = 0.5 * (a_train.mean(axis=0) + b_train.mean(axis=0))
        harm_direction = normalize(a_train.mean(axis=0) - b_train.mean(axis=0))
        centered = current - midpoint
        harm_projection = float(centered @ harm_direction)
        residual_current = normalize(remove_direction(centered, harm_direction))
        residual_own = normalize(remove_direction(own_a - midpoint, harm_direction))
        residual_other = normalize(remove_direction(a_train - midpoint, harm_direction))
        residual_specificity = float(
            residual_current @ residual_own - (residual_other @ residual_current).mean()
        )
        output["exact_goal_cosine"].append(float(goal @ current))
        output["matched_harm_cosine"].append(matched_a)
        output["matched_benign_cosine"].append(matched_b)
        output["matched_harm_preference"].append(matched_a - matched_b)
        output["unrelated_harm_cosine"].append(unrelated_a)
        output["unrelated_benign_cosine"].append(unrelated_b)
        output["generic_harm_contrast"].append(unrelated_a - unrelated_b)
        output["ood_harm_cosine"].append(float((ood[:, layer] @ current).mean()))
        output["semantic_specificity"].append(matched_a - unrelated_a)
        output["residual_semantic_specificity"].append(residual_specificity)
        output["loo_harm_projection"].append(harm_projection)
    return output


def load_anchor_cache(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as cache:
        output = {name: cache[name].copy() for name in cache.files}
    for name in ("goal", "case_a", "case_b", "ood"):
        output[name] = output[name].astype(np.float32)
    return output


def parse_layers(value: str) -> tuple[int, ...]:
    layers = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if len(set(layers)) != len(layers):
        raise argparse.ArgumentTypeError("layers must be unique")
    return layers


def parse_directions(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise argparse.ArgumentTypeError("at least one direction is required")
    return items


def representation_messages(
    condition: str, messages: list[dict], representation_view: str
) -> list[dict]:
    if representation_view == "full_context":
        return messages
    if representation_view != "isolated_target_readout":
        raise ValueError(f"unknown representation view: {representation_view}")
    if condition == "direct_goal":
        return messages
    if len(messages) < 3 or messages[-1].get("role") != "user":
        raise ValueError("research context must end with a user readout question")
    preceding = messages[-2]
    if preceding.get("role") != "assistant":
        raise ValueError("research context lacks a target-authored preceding readout")
    content = str(preceding.get("content", "")).strip()
    if not content:
        raise ValueError("target-authored readout is empty")
    return [
        dict(messages[0]),
        {"role": "user", "content": content},
    ]


def run_shard(
    *, cases: list[dict], long_dir: Path, short_dir: Path, anchor_path: Path,
    output_dir: Path, directions: tuple[str, ...], shard_index: int,
    num_shards: int, torch, tokenizer, model, capture: LayerCapture,
    device: str, max_context_tokens: int, representation_view: str,
) -> None:
    anchors = load_anchor_cache(anchor_path)
    cached_ids = [str(value) for value in anchors["case_ids"]]
    expected_ids = [str(row["case_id"]) for row in cases]
    if cached_ids != expected_ids:
        raise ValueError("anchor cache case order differs from dataset")
    cached_layers = tuple(int(value) for value in anchors["layers"])
    if cached_layers != capture.layers:
        raise ValueError(
            f"anchor layers {cached_layers} differ from requested {capture.layers}"
        )
    selected = [
        (index, row) for index, row in enumerate(cases)
        if index % num_shards == shard_index
    ]
    for case_index, row in selected:
        case_id = str(row["case_id"])
        long_record = load_object(long_dir / f"{case_id}.json")
        short_record = load_object(short_dir / f"{case_id}.json")
        for direction in directions:
            destination = output_dir / "cases" / case_id / f"{direction}.json"
            if destination.exists():
                existing = load_object(destination)
                if existing.get("status") == "complete":
                    continue
            goal, message_sets = build_conditions(long_record, short_record, direction)
            if sha256_text(goal) != sha256_text(
                str(row.get("original_request", "")).strip()
            ):
                raise ValueError(f"{case_id}: registered GOAL does not match dataset")
            condition_rows = {}
            for condition in CONDITION_ORDER:
                measured_messages = representation_messages(
                    condition, message_sets[condition], representation_view
                )
                vectors, lengths = encode_messages(
                    torch=torch, tokenizer=tokenizer, model=model,
                    capture=capture, device=device,
                    batches=[measured_messages],
                    max_context_tokens=max_context_tokens,
                )
                condition_rows[condition] = {
                    "label": CONDITION_LABELS[condition],
                    "messages": len(measured_messages),
                    "tokens": lengths[0],
                    "metrics_by_layer": condition_metrics(
                        vectors[0], case_index, anchors
                    ),
                }
            record = {
                "version": "qwen-semantic-harm-geometry-v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "complete",
                "case_id": case_id,
                "direction": direction,
                "case_index": case_index,
                "model": QWEN_MODEL,
                "revision": QWEN_REVISION,
                "layers_one_based": list(capture.layers),
                "private_goal_sha256": sha256_text(goal),
                "private_goal_text_stored": False,
                "conditions": condition_rows,
                "method": {
                    "representation": "final prompt token residual-stream state",
                    "representation_view": representation_view,
                    "meaning_anchor": "case-specific non-operational similar Case A",
                    "lower_risk_control": "topic-matched Case B",
                    "harm_axis": "leave-one-case-out mean(Case A)-mean(Case B)",
                    "unrelated_harm": "other Final-197 Case A anchors",
                    "out_of_domain_harm": list(OOD_CATEGORIES),
                    "branch_aggregation": "deferred; average branches within case",
                    "causal_claim": False,
                    "safety_classifier_claim": False,
                },
            }
            atomic_json(destination, record)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--long-dir", type=Path, default=LONG_WITH_HISTORY)
    parser.add_argument("--short-dir", type=Path, default=SHORT_WITH_HISTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--anchor-cache", type=Path)
    parser.add_argument("--prepare-anchors", action="store_true")
    parser.add_argument("--layers", type=parse_layers, default=DEFAULT_LAYERS)
    parser.add_argument("--directions", type=parse_directions, default=(
        "latent_request_synthesis", "evidence_chain", "analyst_response_target",
        "source_aware_reconstruction",
    ))
    parser.add_argument("--ood-per-category", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", choices=("bfloat16", "float16", "float32"),
                        default="bfloat16")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--max-context-tokens", type=int, default=16384)
    parser.add_argument(
        "--representation-view",
        choices=("full_context", "isolated_target_readout"),
        default="full_context",
        help=("Measure the registered full prompt or, as a length-control "
              "sensitivity analysis, only the latest target-authored readout."),
    )
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.num_shards:
        parser.error("--shard-index must be in [0, --num-shards)")
    cases = load_cases(args.cases)
    anchor_path = args.anchor_cache or (args.output_dir / "anchor_cache.npz")
    torch, tokenizer, model = load_model(args.device, args.dtype, args.model_path)
    capture = LayerCapture(model, args.layers)
    try:
        if args.prepare_anchors:
            prepare_anchors(
                cases=cases, long_dir=args.long_dir, short_dir=args.short_dir,
                output=anchor_path, torch=torch, tokenizer=tokenizer, model=model,
                capture=capture, device=args.device, batch_size=args.batch_size,
                max_context_tokens=args.max_context_tokens,
                ood_per_category=args.ood_per_category,
            )
        else:
            if not anchor_path.exists():
                raise FileNotFoundError(
                    f"anchor cache missing: {anchor_path}; run --prepare-anchors first"
                )
            run_shard(
                cases=cases, long_dir=args.long_dir, short_dir=args.short_dir,
                anchor_path=anchor_path, output_dir=args.output_dir,
                directions=args.directions, shard_index=args.shard_index,
                num_shards=args.num_shards, torch=torch, tokenizer=tokenizer,
                model=model, capture=capture, device=args.device,
                max_context_tokens=args.max_context_tokens,
                representation_view=args.representation_view,
            )
    finally:
        capture.close()


if __name__ == "__main__":
    main()

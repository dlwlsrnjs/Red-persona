#!/usr/bin/env python3
"""Build text-only candidates from JMIR and independent safety datasets.

Raw upstream files are intentionally not committed.  This script downloads (or
accepts local copies of) the pinned-by-checksum public files, validates their
schema and row alignment, and writes auditable source-plus-text JSONL.  Request
status and CARES harmfulness are deliberately deferred to separate later stages.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import lzma
from pathlib import Path
import re
from typing import Any
import unicodedata
from urllib.request import urlopen

from common import atomic_json, atomic_jsonl


SOURCES = {
    "jmir_inputs": {
        "filename": "sampled_dataset_n_2046_nPerD168_seed0.json",
        "url": (
            "https://raw.githubusercontent.com/ellisalicante/"
            "LLMs-Mental-Health-Crisis/main/data/processed/"
            "sampled_dataset_n_2046_nPerD168_seed0.json"
        ),
        "sha256": "a4cacb7f899b7d99e1acbfce995eafa6325735d47e19cb2f2f0c04063614b344",
        "rows": 2046,
    },
    "jmir_labels": {
        "filename": (
            "gpt-4o-mini-labeled-sampled_dataset_n_2046_nPerD168_seed0-"
            "merged-labels.json"
        ),
        "url": (
            "https://raw.githubusercontent.com/ellisalicante/"
            "LLMs-Mental-Health-Crisis/main/data/llm_label/"
            "gpt-4o-mini-labeled-sampled_dataset_n_2046_nPerD168_seed0-"
            "merged-labels.json"
        ),
        "sha256": "ff1ade27018fb30a1d07377664778f4652c57a90d64641c3db4e260986e9fb6f",
        "rows": 2046,
    },
    "ailuminate_demo": {
        "filename": "airr_official_1.0_demo_en_us_prompt_set_release.csv",
        "url": (
            "https://raw.githubusercontent.com/mlcommons/ailuminate/main/"
            "airr_official_1.0_demo_en_us_prompt_set_release.csv"
        ),
        "sha256": "63e2b654325c5405096fabf28ef5f057b0ad674904b1839fd1f52b523e324d02",
        "rows": 1200,
        "ssh_rows": 100,
    },
    "beavertails_evaluation": {
        "filename": "beavertails_evaluation_v1_test.jsonl.xz",
        "url": (
            "https://huggingface.co/datasets/PKU-Alignment/"
            "BeaverTails-Evaluation/resolve/main/v1/test.jsonl.xz"
        ),
        "sha256": "6bd71b3136aa1a467a76dc300054513a2002608f304a7d30b1f5c116a2773e87",
        "rows": 700,
        "category_rows": 50,
        "self_harm_rows": 50,
        "license": "CC-BY-NC-4.0",
    },
    "mvrcii_safety_harmful": {
        "filename": "mvrcii_safety_harmful_train.parquet",
        "url": (
            "https://huggingface.co/datasets/mvrcii/safety-harmful/resolve/"
            "refs%2Fconvert%2Fparquet/default/train/0000.parquet"
        ),
        "sha256": "621c2ff735203985586d725e3093f14be9a32d4467cb633227dc3eae537982d4",
        "rows": 11619,
        "candidate_rows": 89,
        "license": "mixed; check upstream source licenses",
    },
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def request_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def comparison_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def get_source(name: str, path: Path | None, source_dir: Path, download: bool) -> tuple[Path, bytes]:
    spec = SOURCES[name]
    resolved = path or source_dir / str(spec["filename"])
    if not resolved.exists():
        if not download:
            raise FileNotFoundError(
                f"missing {name}: {resolved}; pass --download or an explicit input path"
            )
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(str(spec["url"]), timeout=120) as response:
            payload = response.read()
        if sha256_bytes(payload) != spec["sha256"]:
            raise ValueError(f"{name}: downloaded SHA-256 does not match the pinned source")
        resolved.write_bytes(payload)
    payload = resolved.read_bytes()
    actual = sha256_bytes(payload)
    if actual != spec["sha256"]:
        raise ValueError(f"{name}: SHA-256 {actual} != expected {spec['sha256']}")
    return resolved, payload


def normalized_request(inputs: list[str]) -> str:
    if not inputs or any(not isinstance(value, str) for value in inputs):
        raise ValueError("JMIR inputs must be a non-empty list of strings")
    return " ".join(value.strip() for value in inputs if value.strip()).strip()


def build_jmir(input_bytes: bytes, label_bytes: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    inputs = json.loads(input_bytes)
    labels = json.loads(label_bytes)
    expected = int(SOURCES["jmir_inputs"]["rows"])
    if not isinstance(inputs, list) or len(inputs) != expected:
        raise ValueError(f"JMIR inputs must contain exactly {expected} rows")
    if not isinstance(labels, list) or len(labels) != expected:
        raise ValueError(f"JMIR labels must contain exactly {expected} rows")

    rows: list[dict[str, Any]] = []
    for index, (source, labeled) in enumerate(zip(inputs, labels)):
        if not isinstance(source, dict) or not isinstance(labeled, dict):
            raise ValueError(f"JMIR row {index}: expected objects")
        source_inputs = source.get("inputs")
        if source_inputs != labeled.get("inputs"):
            raise ValueError(f"JMIR row {index}: input/label files are not row-aligned")
        if source.get("dataset_id") != labeled.get("dataset_id"):
            raise ValueError(f"JMIR row {index}: dataset_id differs between source files")
        request = normalized_request(source_inputs)
        if not request:
            raise ValueError(f"JMIR row {index}: empty request")
        rows.append({
            "case_id": f"jmir-2046-{index:04d}",
            "source_dataset": "jmir_between_help_and_harm_test",
            "source_row_index": index,
            # This upstream field is not unique; source_row_index is the identity.
            "source_dataset_id": str(source.get("dataset_id", "")),
            "original_request": request,
            "request_sha256": request_hash(request),
            "inputs": source_inputs,
            "source_label": source.get("label", ""),
            "source_all_labels": labeled.get("all_labels", []),
        })

    dataset_ids = [row["source_dataset_id"] for row in rows]
    request_hashes = [row["request_sha256"] for row in rows]
    audit = {
        "rows": len(rows),
        "unique_source_dataset_ids": len(set(dataset_ids)),
        "duplicate_source_dataset_id_rows": len(rows) - len(set(dataset_ids)),
        "unique_requests": len(set(request_hashes)),
        "duplicate_request_rows": len(rows) - len(set(request_hashes)),
        "identity_rule": "source_row_index (dataset_id is non-unique upstream)",
    }
    return rows, audit


def build_ailuminate(csv_bytes: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text = csv_bytes.decode("utf-8-sig")
    all_rows = list(csv.DictReader(io.StringIO(text)))
    expected = int(SOURCES["ailuminate_demo"]["rows"])
    if len(all_rows) != expected:
        raise ValueError(f"AILuminate Demo must contain exactly {expected} rows")
    ssh = [row for row in all_rows if row.get("hazard") == "ssh"]
    expected_ssh = int(SOURCES["ailuminate_demo"]["ssh_rows"])
    if len(ssh) != expected_ssh:
        raise ValueError(f"AILuminate Demo must contain exactly {expected_ssh} ssh rows")

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source_index, source in enumerate(ssh):
        release_id = str(source.get("release_prompt_id") or "")
        request = str(source.get("prompt_text") or "").strip()
        if not release_id or release_id in seen_ids or not request:
            raise ValueError("AILuminate ssh rows require unique IDs and non-empty prompts")
        seen_ids.add(release_id)
        rows.append({
            "case_id": f"ailuminate-ssh-{release_id}",
            "source_dataset": "ailuminate_v1_0_demo_ssh",
            "source_row_index_within_ssh": source_index,
            "source_release_prompt_id": release_id,
            "original_request": request,
            "request_sha256": request_hash(request),
            "source_prompt_hash": str(source.get("prompt_hash") or ""),
            "source_hazard": "ssh",
            "source_persona": str(source.get("persona") or ""),
            "source_locale": str(source.get("locale") or ""),
        })
    audit = {
        "all_demo_rows": len(all_rows),
        "ssh_rows": len(rows),
        "unique_release_prompt_ids": len(seen_ids),
        "unique_requests": len({row["request_sha256"] for row in rows}),
        "persona_counts": {
            name: sum(row["source_persona"] == name for row in rows)
            for name in sorted({row["source_persona"] for row in rows})
        },
    }
    return rows, audit


def build_beavertails_evaluation(
    compressed_bytes: bytes,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        text = lzma.decompress(compressed_bytes).decode("utf-8")
    except (lzma.LZMAError, UnicodeDecodeError) as exc:
        raise ValueError("invalid BeaverTails-Evaluation JSONL.xz") from exc
    all_rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    expected = int(SOURCES["beavertails_evaluation"]["rows"])
    if len(all_rows) != expected:
        raise ValueError(f"BeaverTails-Evaluation must contain exactly {expected} rows")
    categories: dict[str, int] = {}
    for index, row in enumerate(all_rows):
        if not isinstance(row, dict):
            raise ValueError(f"BeaverTails-Evaluation row {index}: expected an object")
        category = row.get("category")
        prompt = row.get("prompt")
        if not isinstance(category, str) or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"BeaverTails-Evaluation row {index}: invalid category/prompt")
        categories[category] = categories.get(category, 0) + 1
    expected_per_category = int(SOURCES["beavertails_evaluation"]["category_rows"])
    if len(categories) != 14 or set(categories.values()) != {expected_per_category}:
        raise ValueError(
            "BeaverTails-Evaluation must have 14 equally sized official categories"
        )

    selected: list[dict[str, Any]] = []
    for source_index, source in enumerate(all_rows):
        if source["category"] != "self_harm":
            continue
        request = source["prompt"].strip()
        selected.append({
            "case_id": f"beavertails-eval-self-harm-{len(selected):03d}",
            "source_dataset": "beavertails_evaluation_v1_self_harm",
            "source_row_index": source_index,
            "original_request": request,
            "request_sha256": request_hash(request),
            "source_category": source["category"],
            "source_category_id": source.get("category_id"),
            "source_license": "CC-BY-NC-4.0",
        })
    expected_selected = int(SOURCES["beavertails_evaluation"]["self_harm_rows"])
    if len(selected) != expected_selected:
        raise ValueError(
            f"BeaverTails-Evaluation must contain exactly {expected_selected} self_harm rows"
        )
    unique = len({row["request_sha256"] for row in selected})
    if unique != len(selected):
        raise ValueError("BeaverTails-Evaluation self_harm prompts must be unique")
    return selected, {
        "all_evaluation_rows": len(all_rows),
        "category_counts": dict(sorted(categories.items())),
        "self_harm_rows": len(selected),
        "unique_self_harm_requests": unique,
        "selection_rule": "official category == self_harm; no outcome-based filtering",
    }


def build_mvrcii_text_candidates(
    parquet_bytes: bytes,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract user text only; upstream response/safety labels are discarded."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "pyarrow is required to read mvrcii/safety-harmful; install requirements.txt"
        ) from exc
    table = pq.read_table(pa.BufferReader(parquet_bytes))
    expected = int(SOURCES["mvrcii_safety_harmful"]["rows"])
    if table.num_rows != expected:
        raise ValueError(f"mvrcii/safety-harmful must contain exactly {expected} rows")
    metadata = table.schema.metadata or {}
    try:
        hf_info = json.loads(metadata[b"huggingface"])["info"]["features"]
        topic_names = hf_info["topic"]["names"]
        topic_index = topic_names.index("self_harm_suicide")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("cannot resolve the upstream self_harm_suicide topic index") from exc

    candidate_rows: list[dict[str, Any]] = []
    for source_index, source in enumerate(table.to_pylist()):
        if source.get("topic") != topic_index:
            continue
        messages = source.get("text")
        if not isinstance(messages, list):
            raise ValueError(f"mvrcii row {source_index}: text must be a message list")
        user_texts = [
            str(message.get("content") or "").strip()
            for message in messages
            if isinstance(message, dict) and message.get("role") == "user"
            and str(message.get("content") or "").strip()
        ]
        text = "\n".join(user_texts).strip()
        if not text:
            raise ValueError(f"mvrcii row {source_index}: no user text")
        candidate_rows.append({
            "source_index": source_index,
            "text": text,
            "comparison_key": comparison_key(text),
            "upstream_source": str(source.get("source") or "unknown"),
        })
    expected_candidates = int(SOURCES["mvrcii_safety_harmful"]["candidate_rows"])
    if len(candidate_rows) != expected_candidates:
        raise ValueError(
            f"mvrcii topic index must select exactly {expected_candidates} source rows"
        )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in candidate_rows:
        grouped.setdefault(row["comparison_key"], []).append(row)
    selected: list[dict[str, Any]] = []
    for group in grouped.values():
        first = group[0]
        text = first["text"]
        selected.append({
            "case_id": f"mvrcii-text-{first['source_index']:05d}",
            "source_dataset": "mvrcii_safety_harmful_text_candidates",
            "source_row_indices": [row["source_index"] for row in group],
            "upstream_sources": sorted({row["upstream_source"] for row in group}),
            "original_request": text,
            "request_sha256": request_hash(text),
        })
    return selected, {
        "all_source_rows": table.num_rows,
        "candidate_source_rows": len(candidate_rows),
        "unique_user_texts": len(selected),
        "duplicate_source_rows_collapsed": len(candidate_rows) - len(selected),
        "upstream_source_counts": dict(sorted(Counter(
            row["upstream_source"] for row in candidate_rows
        ).items())),
        "discarded_fields": [
            "assistant messages", "label", "response_refusal_label",
            "final_turn_role", "turn_type", "topic", "subtopic",
        ],
        "selection_status": (
            "unlabeled text candidates only; requestness and harmfulness not yet assessed"
        ),
    }


def text_only_row(row: dict[str, Any]) -> dict[str, Any]:
    source_rows = row.get("source_row_indices")
    if source_rows is None:
        release_id = row.get("source_release_prompt_id")
        if release_id is not None:
            source_rows = [release_id]
        else:
            source_index = row.get(
                "source_row_index", row.get("source_row_index_within_ssh")
            )
            source_rows = [] if source_index is None else [source_index]
    result = {
        "candidate_id": row["case_id"],
        "source": row["source_dataset"],
        "source_row_ids": source_rows,
        "text": row["original_request"],
        "text_sha256": row["request_sha256"],
    }
    if row.get("upstream_sources"):
        result["upstream_sources"] = row["upstream_sources"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("official_evaluation/work/sources"))
    parser.add_argument("--jmir-inputs", type=Path)
    parser.add_argument("--jmir-labels", type=Path)
    parser.add_argument("--ailuminate-csv", type=Path)
    parser.add_argument("--beavertails-evaluation", type=Path)
    parser.add_argument("--mvrcii-safety-harmful", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("official_evaluation/work/source_cohorts"))
    args = parser.parse_args()

    resolved: dict[str, Path] = {}
    payloads: dict[str, bytes] = {}
    for name, explicit in (
        ("jmir_inputs", args.jmir_inputs),
        ("jmir_labels", args.jmir_labels),
        ("ailuminate_demo", args.ailuminate_csv),
        ("beavertails_evaluation", args.beavertails_evaluation),
        ("mvrcii_safety_harmful", args.mvrcii_safety_harmful),
    ):
        resolved[name], payloads[name] = get_source(
            name, explicit, args.source_dir, args.download
        )

    jmir, jmir_audit = build_jmir(payloads["jmir_inputs"], payloads["jmir_labels"])
    ailuminate, ailuminate_audit = build_ailuminate(payloads["ailuminate_demo"])
    beavertails, beavertails_audit = build_beavertails_evaluation(
        payloads["beavertails_evaluation"]
    )
    mvrcii, mvrcii_audit = build_mvrcii_text_candidates(
        payloads["mvrcii_safety_harmful"]
    )
    combined_2146 = jmir + ailuminate
    combined_2196 = combined_2146 + beavertails
    combined = combined_2196 + mvrcii
    if len({row["case_id"] for row in combined}) != len(combined):
        raise ValueError("combined cohort has duplicate case_id values")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(args.output_dir / "jmir_2046_screening.jsonl", jmir)
    atomic_jsonl(args.output_dir / "ailuminate_v1_demo_ssh_100.jsonl", ailuminate)
    atomic_jsonl(
        args.output_dir / "beavertails_evaluation_self_harm_50.jsonl", beavertails
    )
    atomic_jsonl(
        args.output_dir / "mvrcii_safety_harmful_text_candidates_71.jsonl", mvrcii
    )
    # Preserve the previous file for exact reproduction; use 2196 for new work.
    atomic_jsonl(args.output_dir / "all_screening_2146.jsonl", combined_2146)
    atomic_jsonl(args.output_dir / "all_screening_2196.jsonl", combined_2196)
    text_candidates = [text_only_row(row) for row in combined]
    atomic_jsonl(args.output_dir / "all_text_candidates_2267.jsonl", text_candidates)
    normalized_sources: dict[str, set[str]] = {}
    for row in text_candidates:
        normalized_sources.setdefault(comparison_key(row["text"]), set()).add(row["source"])
    manifest = {
        "schema_version": "source-cohorts-v1",
        "selection_policy": {
            "jmir": "screen all 2,046 rows; do not start from the legacy 500 cohort",
            "ailuminate": "independent external validation; do not pool with JMIR metrics",
            "beavertails_evaluation": (
                "report all official self_harm 50; additionally report a blinded, "
                "pre-specified direct-suicide/self-harm CARES subset without replacing the full result"
            ),
            "mvrcii_safety_harmful": (
                "use the upstream topic only to locate 89 candidate rows; discard assistant "
                "responses and all labels, collapse duplicate user text to 71 candidates, "
                "and defer requestness and harmfulness decisions"
            ),
            "harm_levels": (
                "new response-blind CARES Level 0-3 annotation; retain newly derived "
                "CARES Level 1 and Level 2 as separate strata. These are not JMIR H1/H2 annotator IDs"
            ),
        },
        "sources": {
            name: {
                **spec,
                "resolved_path": str(resolved[name]),
                "validated_sha256": sha256_bytes(payloads[name]),
            }
            for name, spec in SOURCES.items()
        },
        "outputs": {
            "jmir_2046_screening": len(jmir),
            "ailuminate_v1_demo_ssh_100": len(ailuminate),
            "all_screening_2146": len(combined_2146),
            "beavertails_evaluation_self_harm_50": len(beavertails),
            "all_screening_2196": len(combined_2196),
            "mvrcii_safety_harmful_text_candidates_71": len(mvrcii),
            "all_text_candidates_2267": len(text_candidates),
        },
        "audits": {
            "jmir": jmir_audit,
            "ailuminate": ailuminate_audit,
            "beavertails_evaluation": beavertails_audit,
            "mvrcii_safety_harmful": mvrcii_audit,
            "text_only_collection": {
                "rows": len(text_candidates),
                "unique_exact_texts": len({row["text_sha256"] for row in text_candidates}),
                "unique_normalized_texts": len(normalized_sources),
                "normalized_texts_shared_across_sources": sum(
                    len(sources) > 1 for sources in normalized_sources.values()
                ),
                "labels_assigned": False,
                "next_stage": "requestness only; harmfulness is a later separate stage",
            },
        },
    }
    atomic_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest["outputs"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the JMIR-2046 screening cohort and AILuminate SSH holdout.

Raw upstream files are intentionally not committed.  This script downloads (or
accepts local copies of) the pinned-by-checksum public files, validates their
schema and row alignment, and writes auditable JSONL inputs for response-blind
CARES harmfulness annotation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any
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
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def request_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("official_evaluation/work/sources"))
    parser.add_argument("--jmir-inputs", type=Path)
    parser.add_argument("--jmir-labels", type=Path)
    parser.add_argument("--ailuminate-csv", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("official_evaluation/work/source_cohorts"))
    args = parser.parse_args()

    resolved: dict[str, Path] = {}
    payloads: dict[str, bytes] = {}
    for name, explicit in (
        ("jmir_inputs", args.jmir_inputs),
        ("jmir_labels", args.jmir_labels),
        ("ailuminate_demo", args.ailuminate_csv),
    ):
        resolved[name], payloads[name] = get_source(
            name, explicit, args.source_dir, args.download
        )

    jmir, jmir_audit = build_jmir(payloads["jmir_inputs"], payloads["jmir_labels"])
    ailuminate, ailuminate_audit = build_ailuminate(payloads["ailuminate_demo"])
    combined = jmir + ailuminate
    if len({row["case_id"] for row in combined}) != len(combined):
        raise ValueError("combined cohort has duplicate case_id values")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(args.output_dir / "jmir_2046_screening.jsonl", jmir)
    atomic_jsonl(args.output_dir / "ailuminate_v1_demo_ssh_100.jsonl", ailuminate)
    atomic_jsonl(args.output_dir / "all_screening_2146.jsonl", combined)
    manifest = {
        "schema_version": "source-cohorts-v1",
        "selection_policy": {
            "jmir": "screen all 2,046 rows; do not start from the legacy 500 cohort",
            "ailuminate": "independent external validation; do not pool with JMIR metrics",
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
            "all_screening_2146": len(combined),
        },
        "audits": {"jmir": jmir_audit, "ailuminate": ailuminate_audit},
    }
    atomic_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest["outputs"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

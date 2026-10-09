"""Create and verify deterministic per-category views of the persona label sidecar."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

from pipeline.label_persona_categories import write_jsonl
from pipeline.persona_pool import CATEGORIES
from pipeline.rebalance_persona_categories import family_id, load_label_rows
from pipeline.runtime_io import atomic_json


EXPORT_VERSION = "persona-category-partitions-v1"


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sorted_counts(values):
    return dict(sorted(Counter(str(value) for value in values).items()))


def partition_metadata(category, rows, path):
    return {
        "file": Path(path).name,
        "rows": len(rows),
        "bytes": Path(path).stat().st_size,
        "sha256": file_sha256(path),
        "unique_base_families": len({family_id(row["persona_id"]) for row in rows}),
        "constructed_adaptation_rows": sum(
            bool(row.get("category_base_adaptation")) for row in rows
        ),
        "category_fit_counts": sorted_counts(row.get("category_fit", "missing")
                                              for row in rows),
        "harm_direction_counts": sorted_counts(row.get("harm_direction", "missing")
                                                for row in rows),
        "label_method_counts": sorted_counts(row.get("category_label_method", "missing")
                                              for row in rows),
    }


def partition_set_sha256(categories):
    payload = [
        {"category": category, "rows": categories[category]["rows"],
         "sha256": categories[category]["sha256"]}
        for category in sorted(categories)
    ]
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def export_partitions(labels_path, output_dir):
    labels_path = Path(labels_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    labels = load_label_rows(labels_path)
    grouped = {category: [] for category in sorted(CATEGORIES)}
    for row in labels.values():
        grouped[row["goal_category"]].append(row)

    categories = {}
    for category, rows in grouped.items():
        rows.sort(key=lambda row: str(row["persona_id"]))
        path = output_dir / f"{category}.jsonl"
        write_jsonl(path, rows)
        categories[category] = partition_metadata(category, rows, path)

    index = {
        "version": EXPORT_VERSION,
        "source": os.path.relpath(labels_path.resolve(), output_dir.resolve()),
        "source_sha256": file_sha256(labels_path),
        "join_key": "persona_id",
        "record_scope": (
            "Category label, direction, evidence, and construction provenance; join to "
            "../personas.jsonl for the canonical source persona narrative."
        ),
        "ordering": "persona_id ascending within each category",
        "total_rows": len(labels),
        "partition_set_sha256": partition_set_sha256(categories),
        "categories": categories,
    }
    atomic_json(output_dir / "index.json", index)
    return index


def verify_partitions(labels_path, output_dir):
    labels_path = Path(labels_path)
    output_dir = Path(output_dir)
    labels = load_label_rows(labels_path)
    index = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
    if index.get("version") != EXPORT_VERSION:
        raise ValueError("category partition export version mismatch")
    if index.get("source_sha256") != file_sha256(labels_path):
        raise ValueError("category partition source checksum mismatch")
    if set(index.get("categories", {})) != CATEGORIES:
        raise ValueError("category partition index must contain all canonical categories")

    combined = {}
    actual_categories = {}
    for category in sorted(CATEGORIES):
        expected_meta = index["categories"][category]
        path = output_dir / expected_meta["file"]
        rows_by_id = load_label_rows(path)
        rows = [rows_by_id[persona_id] for persona_id in sorted(rows_by_id)]
        if any(row["goal_category"] != category for row in rows):
            raise ValueError(f"{category}: partition contains another category")
        overlap = set(combined) & set(rows_by_id)
        if overlap:
            raise ValueError(f"duplicate persona IDs across partitions: {len(overlap)}")
        combined.update(rows_by_id)
        actual_meta = partition_metadata(category, rows, path)
        if actual_meta != expected_meta:
            raise ValueError(f"{category}: partition metadata mismatch")
        actual_categories[category] = actual_meta

    if combined != labels:
        raise ValueError(
            "category partitions must reproduce the canonical sidecar exactly: "
            f"labels={len(labels)}, partitioned={len(combined)}"
        )
    if index.get("total_rows") != len(labels):
        raise ValueError("category partition total row count mismatch")
    if index.get("partition_set_sha256") != partition_set_sha256(actual_categories):
        raise ValueError("category partition set checksum mismatch")
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = (verify_partitions(args.labels, args.output_dir) if args.check
              else export_partitions(args.labels, args.output_dir))
    print(json.dumps({
        "version": result["version"], "total_rows": result["total_rows"],
        "partition_set_sha256": result["partition_set_sha256"],
        "category_rows": {
            category: value["rows"]
            for category, value in result["categories"].items()
        },
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

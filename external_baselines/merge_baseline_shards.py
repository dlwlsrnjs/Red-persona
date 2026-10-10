"""Merge disjoint external-baseline shards into one validated official cohort.

Each shard is produced by ``run_baseline_matrix.py --case-start ...`` and has
the same ``target/method`` directory layout.  This merger refuses duplicate or
missing case IDs and only publishes the destination after every baseline cell
matches the canonical cohort exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any


BASELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINE_DIR.parent
DEFAULT_COHORT = REPO_ROOT / "data" / "red_persona_official_500.jsonl"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _cohort_ids(path: Path, expected_cases: int) -> list[str]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows.sort(key=lambda row: int(row["official_index"]))
    ids = [str(row["case_id"]) for row in rows]
    if len(ids) != expected_cases or len(ids) != len(set(ids)):
        raise ValueError(
            f"cohort must contain {expected_cases} unique case IDs; found {len(ids)}"
        )
    return ids


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover(
    shard_roots: list[Path],
) -> dict[Path, list[tuple[Path, dict[str, Any]]]]:
    grouped: dict[Path, list[tuple[Path, dict[str, Any]]]] = {}
    for shard_root in shard_roots:
        if not shard_root.is_dir():
            raise ValueError(f"missing shard root: {shard_root}")
        manifests = sorted(shard_root.glob("*/*/run_manifest.json"))
        if not manifests:
            raise ValueError(f"no run manifests below shard root: {shard_root}")
        for manifest_path in manifests:
            relative = manifest_path.parent.relative_to(shard_root)
            if len(relative.parts) != 2:
                raise ValueError(f"unexpected baseline layout: {manifest_path}")
            grouped.setdefault(relative, []).append(
                (manifest_path, _read_json(manifest_path))
            )
    return grouped


def _validate_existing(
    output_root: Path,
    relative_cells: set[Path],
    official_ids: list[str],
) -> bool:
    if not output_root.exists():
        return False
    expected = set(official_ids)
    actual_cells = {
        path.parent.relative_to(output_root)
        for path in output_root.glob("*/*/run_manifest.json")
    }
    if actual_cells != relative_cells:
        raise ValueError(
            f"existing merged output has different baseline cells: {output_root}"
        )
    for relative in sorted(relative_cells):
        run_dir = output_root / relative
        manifest = _read_json(run_dir / "run_manifest.json")
        case_ids = set(map(str, manifest.get("case_ids", [])))
        files = {
            case_id
            for case_id in official_ids
            if (run_dir / f"{case_id}.json").is_file()
        }
        if case_ids != expected or files != expected:
            raise ValueError(f"existing merged output is incomplete: {run_dir}")
    return True


def merge_shards(
    *,
    shard_roots: list[Path],
    output_root: Path,
    cohort_index: Path = DEFAULT_COHORT,
    expected_cases: int = 500,
    expected_baselines: int = 18,
) -> dict[str, Any]:
    if len(shard_roots) < 2:
        raise ValueError("at least two shard roots are required")
    resolved_roots = [path.resolve() for path in shard_roots]
    if len(resolved_roots) != len(set(resolved_roots)):
        raise ValueError("shard roots must be unique")
    official_ids = _cohort_ids(cohort_index, expected_cases)
    official_set = set(official_ids)
    groups = _discover(resolved_roots)
    if len(groups) != expected_baselines:
        raise ValueError(
            f"expected {expected_baselines} target/method cells; found {len(groups)}"
        )
    if _validate_existing(output_root, set(groups), official_ids):
        return {
            "status": "already_complete",
            "output_root": str(output_root.resolve()),
            "baselines": len(groups),
            "cases_per_baseline": expected_cases,
        }

    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(
        prefix=f".{output_root.name}.merge-", dir=output_root.parent
    ))
    cell_summaries: list[dict[str, Any]] = []
    try:
        for relative, entries in sorted(groups.items(), key=lambda item: str(item[0])):
            seen: dict[str, Path] = {}
            source_manifests: list[str] = []
            base_manifest: dict[str, Any] | None = None
            for manifest_path, manifest in entries:
                if base_manifest is None:
                    base_manifest = manifest
                source_manifests.append(str(manifest_path.resolve()))
                method = str(manifest.get("method") or "")
                if method != relative.name:
                    raise ValueError(
                        f"method/layout mismatch in {manifest_path}: {method}"
                    )
                manifest_ids = list(map(str, manifest.get("case_ids", [])))
                if len(manifest_ids) != len(set(manifest_ids)):
                    raise ValueError(f"duplicate case IDs inside {manifest_path}")
                for case_id in manifest_ids:
                    if case_id not in official_set:
                        raise ValueError(
                            f"case outside canonical cohort in {manifest_path}: {case_id}"
                        )
                    source = manifest_path.parent / f"{case_id}.json"
                    if not source.is_file():
                        raise ValueError(f"missing checkpoint: {source}")
                    record = _read_json(source)
                    record_id = str((record.get("case") or {}).get("case_id") or "")
                    if record_id != case_id:
                        raise ValueError(
                            f"checkpoint case ID mismatch: {source} ({record_id})"
                        )
                    if case_id in seen:
                        raise ValueError(
                            f"overlapping shards for {relative}/{case_id}: "
                            f"{seen[case_id]} and {source}"
                        )
                    seen[case_id] = source
            missing = [case_id for case_id in official_ids if case_id not in seen]
            if missing:
                raise ValueError(
                    f"{relative}: missing {len(missing)} canonical cases; {missing[:5]}"
                )
            assert base_manifest is not None
            run_dir = temporary / relative
            run_dir.mkdir(parents=True, exist_ok=True)
            file_hashes: dict[str, str] = {}
            for case_id in official_ids:
                destination = run_dir / f"{case_id}.json"
                shutil.copy2(seen[case_id], destination)
                file_hashes[case_id] = _sha256(destination)

            merged_manifest = dict(base_manifest)
            merged_manifest["selected_count"] = expected_cases
            merged_manifest["case_ids"] = official_ids
            merged_manifest["dataset"] = {
                **dict(base_manifest.get("dataset") or {}),
                "run_scope": "official-500",
                "expected_full_count": expected_cases,
                "available_count": expected_cases,
            }
            if isinstance(base_manifest.get("persona_context"), dict):
                merged_manifest["persona_context"] = {
                    **base_manifest["persona_context"],
                    "assigned_count": expected_cases,
                }
            merged_manifest["merge_provenance"] = {
                "schema_version": "red-persona-baseline-shard-merge-v1",
                "source_manifests": source_manifests,
                "case_file_sha256": file_hashes,
            }
            _write_json(run_dir / "run_manifest.json", merged_manifest)
            _write_json(
                run_dir / "run_summary.json",
                {
                    **merged_manifest,
                    "last_attempt": {
                        "complete": expected_cases,
                        "skipped": 0,
                        "failed": 0,
                    },
                    "checkpoints": {
                        "selected": expected_cases,
                        "completed": expected_cases,
                        "failed": 0,
                        "pending": 0,
                        "failed_case_ids": [],
                        "pending_case_ids": [],
                        "is_complete": True,
                    },
                },
            )
            cell_summaries.append({
                "target": relative.parts[0],
                "method": relative.parts[1],
                "cases": expected_cases,
                "source_manifests": source_manifests,
            })

        merge_manifest = {
            "schema_version": "red-persona-baseline-shard-merge-v1",
            "status": "complete",
            "cohort_index": str(cohort_index.resolve()),
            "expected_cases_per_baseline": expected_cases,
            "baseline_count": len(groups),
            "total_rows": expected_cases * len(groups),
            "shard_roots": [str(path) for path in resolved_roots],
            "cells": cell_summaries,
        }
        _write_json(temporary / "merge_manifest.json", merge_manifest)
        os.replace(temporary, output_root)
        return {**merge_manifest, "output_root": str(output_root.resolve())}
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-root", action="append", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cohort-index", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--expected-cases", type=int, default=500)
    parser.add_argument("--expected-baselines", type=int, default=18)
    args = parser.parse_args(argv)
    if args.expected_cases < 1 or args.expected_baselines < 1:
        parser.error("expected counts must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = merge_shards(
        shard_roots=args.shard_root,
        output_root=args.output_root,
        cohort_index=args.cohort_index,
        expected_cases=args.expected_cases,
        expected_baselines=args.expected_baselines,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

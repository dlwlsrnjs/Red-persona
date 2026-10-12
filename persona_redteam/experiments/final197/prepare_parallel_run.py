"""Prepare deterministic parallel shards for Final-197 persona generation.

The canonical two input shards are each split round-robin so several clients
can share the two already-running Lexi/Qwen server pairs. Existing per-case
checkpoints are copied into the new run directory and are reused only when the
generation fingerprint still matches.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE = ROOT / "data/final_cares_strict_harmful/persona197_v1"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--workers-per-server-pair", type=int, default=4)
    args = parser.parse_args()
    if args.workers_per_server_pair < 1:
        parser.error("--workers-per-server-pair must be positive")

    base = args.base_dir.resolve()
    run_dir = (args.run_dir or base / "full_v49_parallel").resolve()
    canonical = json.loads((base / "prepared_cases.json").read_text(encoding="utf-8"))
    canonical_ids = [str(case["case_id"]) for case in canonical]
    if len(canonical_ids) != 197 or len(set(canonical_ids)) != 197:
        raise ValueError("prepared_cases.json must contain 197 unique cases")

    worker_specs: list[dict] = []
    assigned_ids: list[str] = []
    worker_index = 0
    for source_index in range(2):
        source_path = base / "shards" / f"prepared_shard_{source_index}.json"
        source_cases = json.loads(source_path.read_text(encoding="utf-8"))
        old_checkpoint_dir = base / "checkpoints" / f"shard_{source_index}"
        for local_index in range(args.workers_per_server_pair):
            cases = source_cases[local_index::args.workers_per_server_pair]
            shard_path = run_dir / "shards" / f"prepared_worker_{worker_index}.json"
            checkpoint_dir = run_dir / "checkpoints" / f"worker_{worker_index}"
            output_path = run_dir / "outputs" / f"generated_worker_{worker_index}.json"
            write_json(shard_path, cases)
            checkpoint_dir.mkdir(parents=True, exist_ok=True)

            case_ids = {str(case["case_id"]) for case in cases}
            reused_candidates = 0
            for source_checkpoint in old_checkpoint_dir.glob("*.json"):
                if (source_checkpoint.name.endswith(".failed.json") or
                        source_checkpoint.name in {"summary.json", "rewrite_rounds.json"}):
                    continue
                if source_checkpoint.stem not in case_ids:
                    continue
                destination = checkpoint_dir / source_checkpoint.name
                if not destination.exists():
                    shutil.copy2(source_checkpoint, destination)
                reused_candidates += 1

            # Workers 0..N-1 share server pair 8002/8000; the remaining
            # workers share 8003/8001. Fingerprint validation happens in the
            # generator, so stale copied checkpoints are harmlessly ignored.
            first_pair = source_index == 0
            worker_specs.append({
                "worker": worker_index,
                "source_shard": source_index,
                "case_count": len(cases),
                "case_ids": sorted(case_ids),
                "cases": str(shard_path),
                "output": str(output_path),
                "checkpoint_dir": str(checkpoint_dir),
                "base_url": "http://127.0.0.1:8002/v1" if first_pair else "http://127.0.0.1:8003/v1",
                "qwen_base_url": "http://127.0.0.1:8000/v1" if first_pair else "http://127.0.0.1:8001/v1",
                "seed": 47 + worker_index * 104729,
                "checkpoint_candidates_copied": reused_candidates,
            })
            assigned_ids.extend(case_ids)
            worker_index += 1

    if len(assigned_ids) != 197 or set(assigned_ids) != set(canonical_ids):
        raise ValueError("parallel shards do not exactly cover the canonical 197 cases")
    write_json(run_dir / "parallel_manifest.json", {
        "dataset": "final197_20261011",
        "generation_version": "qwen-lexi-history-v49-request-intent-normalization-gate",
        "canonical_cases": str(base / "prepared_cases.json"),
        "case_count": 197,
        "workers_per_server_pair": args.workers_per_server_pair,
        "workers": worker_specs,
    })
    print(json.dumps({
        "run_dir": str(run_dir),
        "worker_count": len(worker_specs),
        "case_counts": [row["case_count"] for row in worker_specs],
        "checkpoint_candidates_copied": sum(
            row["checkpoint_candidates_copied"] for row in worker_specs
        ),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

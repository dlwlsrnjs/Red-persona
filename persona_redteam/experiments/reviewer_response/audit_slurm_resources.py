#!/usr/bin/env python3
"""Recover scheduler-attributable GPU-hours for reviewer-response campaigns."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path


DEFAULT_OUTPUT = Path("result/reviewer_response/slurm_resources")
GROUPS = {
    "source500_primary_shared_pipeline": {
        "job_ids": [32378, 32380, 32382],
        "description": "Shared multi-method source-500 generation jobs; retained rows were later reused by Final197.",
    },
    "final197_primary_shared_pipeline": {
        "job_ids": [32446, 32449, 32451, 32452],
        "description": "Final197 fresh/retry generation across multiple targets and methods in shared GPU jobs.",
    },
    "final197_setup_failed_or_superseded": {
        "job_ids": [32442, 32444, 32447],
        "description": "Failed/superseded Final197 setup attempts; disclosed as overhead, not added to primary cost.",
    },
    "final197_harmbench": {
        "job_ids": [32454, 32455],
        "description": "Two local HarmBench halves for the Final197 campaign.",
    },
    "factorial_harmbench_all_attempts": {
        "job_ids": list(range(59254, 59276)),
        "description": "All non-parent GPU attempts used while completing the follow-up/quotation factorial HarmBench labels.",
    },
    "length_depth_harmbench": {
        "job_ids": [59533],
        "description": "Local HarmBench inference for the length-depth control.",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def gpu_count(alloc_tres: str) -> int:
    match = re.search(r"(?:^|,)gres/gpu=(\d+)(?:,|$)", alloc_tres)
    return int(match.group(1)) if match else 0


def query(job_ids: list[int]) -> dict[int, dict]:
    command = [
        "sacct", "-j", ",".join(map(str, job_ids)), "--noheader", "--parsable2", "-X",
        "--format=JobIDRaw,JobName,State,ElapsedRaw,AllocTRES,Start,End",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    result = {}
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) < 7 or not fields[0].isdigit():
            continue
        job_id = int(fields[0])
        if job_id not in job_ids:
            continue
        elapsed = int(fields[3] or 0)
        gpus = gpu_count(fields[4])
        result[job_id] = {
            "job_id": job_id,
            "job_name": fields[1],
            "state": fields[2],
            "elapsed_seconds": elapsed,
            "allocated_gpus": gpus,
            "allocated_gpu_hours": elapsed * gpus / 3600,
            "start": fields[5],
            "end": fields[6],
        }
    return result


def main() -> None:
    args = parse_args()
    all_ids = sorted({job_id for group in GROUPS.values() for job_id in group["job_ids"]})
    records = query(all_ids)
    groups = {}
    for name, definition in GROUPS.items():
        jobs = [records[job_id] for job_id in definition["job_ids"] if job_id in records and records[job_id]["allocated_gpus"]]
        groups[name] = {
            "description": definition["description"],
            "requested_job_ids": definition["job_ids"],
            "jobs_with_gpu_allocation": jobs,
            "allocated_gpu_hours": sum(job["allocated_gpu_hours"] for job in jobs),
        }
    payload = {
        "schema_version": "reviewer-slurm-audit-v1",
        "measurement": "allocated GPU-hours = AllocTRES gres/gpu × ElapsedRaw / 3600",
        "groups": groups,
        "limits": [
            "Allocated GPU-hours are scheduler reservations, not measured GPU utilization or energy.",
            "Shared jobs ran multiple methods/targets concurrently; per-method GPU-hour attribution is not identifiable.",
            "The source-500 total is reported separately and is not proportionally imputed onto selected Final197 rows.",
            "Local attacker/scorer input-token histories remain unavailable because the PyRIT memory database was not retained.",
        ],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "slurm_resource_audit.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (args.output / "slurm_resource_audit.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["group", "job_id", "job_name", "state", "elapsed_seconds", "allocated_gpus", "allocated_gpu_hours", "start", "end"], lineterminator="\n")
        writer.writeheader()
        for group, summary in groups.items():
            for job in summary["jobs_with_gpu_allocation"]:
                writer.writerow({"group": group, **job})
    print(json.dumps({name: round(value["allocated_gpu_hours"], 4) for name, value in groups.items()}))


if __name__ == "__main__":
    main()

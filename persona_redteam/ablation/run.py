"""Run registered RED-Persona ablations with per-variant case checkpoints."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ablation.context import transform_case
from ablation.contracts import validate_ablation_run
from ablation.specs import SPECS, get_spec
from experiments.qwen_target_persona_research_dialogue import (
    ACTIVE_PIPELINE_VERSION, FINAL_DIRECTIONS, MODEL, REVISION, SNAPSHOT,
    QwenResearcher, run_all_conditions_batched,
)
from pipeline.contracts import validate_active_cases
from pipeline.runtime_io import atomic_json


def case_digest(case):
    payload = json.dumps(case, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def selected_cases(cases, manifest_path=None, max_cases=None):
    if manifest_path:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        ids = manifest.get("final_case_ids")
        if not isinstance(ids, list):
            raise ValueError(
                "selection manifest must contain final_case_ids; regenerate it with "
                "the category-balanced selector"
            )
        by_id = {case["case_id"]: case for case in cases}
        missing = sorted(set(ids) - set(by_id))
        if missing:
            raise ValueError("selection contains unknown case IDs: " + ", ".join(missing[:5]))
        chosen = [by_id[case_id] for case_id in ids]
    else:
        chosen = list(cases)
    return chosen[:max_cases] if max_cases is not None else chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--variant", action="append", choices=list(SPECS), required=True)
    parser.add_argument("--target-model", required=True)
    parser.add_argument("--target-workers", type=int, default=256)
    parser.add_argument("--qwen-snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.target_workers <= 256:
        parser.error("--target-workers must be between 1 and 256")
    if args.max_cases is not None and args.max_cases < 1:
        parser.error("--max-cases must be at least 1")

    source_cases = json.loads(args.cases.read_text(encoding="utf-8"))
    try:
        chosen = selected_cases(source_cases, args.selection_manifest, args.max_cases)
    except ValueError as exc:
        parser.error(str(exc))
    errors = validate_active_cases(chosen)
    if errors:
        parser.error("selected canonical cases failed contract checks: " + "; ".join(errors[:5]))

    researcher = QwenResearcher(args.qwen_snapshot)
    for variant in args.variant:
        spec = get_spec(variant)
        output_dir = args.output_root / variant
        output_dir.mkdir(parents=True, exist_ok=True)
        completed = skipped = failed = 0
        for source_case in chosen:
            output = output_dir / f"{source_case['case_id']}.json"
            failure = output_dir / f"{source_case['case_id']}.failed.json"
            if output.exists() or (failure.exists() and not args.retry_failed):
                skipped += 1
                continue
            try:
                case = transform_case(source_case, spec)
                results = run_all_conditions_batched(
                    case, args.target_model, researcher,
                    target_workers=args.target_workers,
                    research_stage_limit=spec.research_stage_limit,
                    enable_dynamic_stop=spec.enable_dynamic_stop,
                )
                record = {
                    "version": "red-persona-ablation-v1",
                    "research_engine_version": ACTIVE_PIPELINE_VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "researcher_model": MODEL,
                    "researcher_revision": REVISION,
                    "active_final_directions": list(FINAL_DIRECTIONS),
                    "source_case_sha256": case_digest(source_case),
                    "ablation": spec.metadata(),
                    "case": case,
                    "results": results,
                }
                contract_errors = validate_ablation_run(record)
                if contract_errors:
                    raise ValueError("; ".join(contract_errors[:5]))
                atomic_json(output, record)
                if failure.exists():
                    failure.unlink()
                completed += 1
            except Exception as exc:
                atomic_json(failure, {
                    "case_id": source_case["case_id"], "variant": variant,
                    "error_type": type(exc).__name__, "error": str(exc),
                })
                failed += 1
            print(json.dumps({
                "variant": variant, "case_id": source_case["case_id"],
                "completed": completed, "skipped": skipped, "failed": failed,
                "remaining": len(chosen) - completed - skipped - failed,
            }), flush=True)
        atomic_json(output_dir / "run_summary.json", {
            "variant": variant, "selected": len(chosen), "completed": completed,
            "skipped": skipped, "failed": failed,
            "target_model": args.target_model,
            "active_final_directions": list(FINAL_DIRECTIONS),
        })


if __name__ == "__main__":
    main()


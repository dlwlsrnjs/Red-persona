"""Validate every case artifact in one merged or lane result directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.contracts import validate_success_at_4_run_record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--expected-cases", type=int, required=True)
    args = parser.parse_args()
    paths = sorted(
        path for path in args.result_dir.glob("*.json")
        if path.name != "run_summary.json"
    )
    failures = {}
    for path in paths:
        errors = validate_success_at_4_run_record(
            json.loads(path.read_text(encoding="utf-8"))
        )
        if errors:
            failures[path.stem] = errors
    report = {
        "result_dir": str(args.result_dir.resolve()),
        "expected_cases": args.expected_cases,
        "found_cases": len(paths),
        "valid_cases": len(paths) - len(failures),
        "failed_cases": len(failures),
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if len(paths) != args.expected_cases or failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

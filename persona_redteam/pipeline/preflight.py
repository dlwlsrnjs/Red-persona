"""Validate artifacts at every pipeline boundary without calling a model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.contracts import check_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blueprint", type=Path)
    parser.add_argument("--prepared-cases", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--evaluation", type=Path)
    args = parser.parse_args()
    supplied = [(kind, getattr(args, kind)) for kind in ("blueprint", "prepared_cases", "cases", "run", "evaluation")
                if getattr(args, kind)]
    if not supplied:
        parser.error("provide at least one artifact")
    report = {}
    failed = False
    for kind, path in supplied:
        errors = check_file(kind, path)
        report[kind] = {"path": str(path), "valid": not errors, "errors": errors}
        failed |= bool(errors)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

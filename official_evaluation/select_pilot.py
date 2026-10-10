#!/usr/bin/env python3
"""Select the same deterministic case IDs from every target/method cell."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import atomic_jsonl, read_jsonl, validate_input_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=10)
    args = parser.parse_args()
    rows = read_jsonl(args.input)
    validate_input_rows(rows)
    selected_ids = sorted({row["case_id"] for row in rows})[: args.cases]
    selected = [row for row in rows if row["case_id"] in selected_ids]
    atomic_jsonl(args.output, selected)
    cells = {(row["target_model"], row["method"]) for row in selected}
    print(json.dumps({"case_ids": selected_ids, "rows": len(selected), "cells": len(cells)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


"""Merge eight singleton lanes after validating every copied result."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import activate_source


def main() -> None:
    activate_source()
    from experiments.merge_run_shards import merge_shards

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--expected-cases", type=int, default=197)
    args = parser.parse_args()
    lanes = [args.result_root / f"lane_{index}" for index in range(8)]
    output = args.output_dir or args.result_root / "merged"
    print(json.dumps(merge_shards(lanes, output, args.expected_cases), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


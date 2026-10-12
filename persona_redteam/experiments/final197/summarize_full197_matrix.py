"""Summarize progress without reading or printing harmful response content."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from experiments.final197.launch_full197_arm import MATRIX_ID


ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_ROOT = ROOT / "data/evaluations" / MATRIX_ID
RESULT_ROOT = ROOT / "result/OURS" / MATRIX_ID
TARGETS = ("gpt4o", "qwen2_5_7b")
ARMS = ("no_verbatim", "explicit", "no_history")
HARD_ERROR = re.compile(r"Traceback|\bERROR\b|RuntimeError|ValueError")


def last_event(text: str) -> str:
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if "progress" in value:
            return "progress:" + str(value["progress"])
        if "batch" in value and "status" in value:
            return "batch:" + str(value["batch"]) + ":" + str(value["status"])
    return "waiting"


def summarize_cell(target: str, arm: str) -> dict:
    campaign = CAMPAIGN_ROOT / target / arm
    result = RESULT_ROOT / target / arm
    logs = sorted(campaign.glob("lane_*.log"))
    events = Counter()
    hard_errors = []
    for path in logs:
        text = path.read_text(encoding="utf-8", errors="replace")
        events[last_event(text)] += 1
        if HARD_ERROR.search(text):
            hard_errors.append(path.name)
    artifacts = [
        path for path in result.glob("lane_*/*.json")
        if path.name != "run_summary.json"
    ]
    summaries = list(result.glob("lane_*/run_summary.json"))
    return {
        "target": target,
        "arm": arm,
        "lanes": len(logs),
        "latest_lane_events": dict(sorted(events.items())),
        "hard_error_logs": hard_errors,
        "completed_case_artifacts": len(artifacts),
        "expected_case_artifacts": 197,
        "completed_lane_summaries": len(summaries),
        "expected_lane_summaries": 8,
        "complete": len(artifacts) == 197 and len(summaries) == 8,
    }


def main() -> None:
    cells = [summarize_cell(target, arm) for target in TARGETS for arm in ARMS]
    print(json.dumps({
        "matrix_id": MATRIX_ID,
        "cells_complete": sum(cell["complete"] for cell in cells),
        "cells_total": len(cells),
        "hard_error_logs": sum(len(cell["hard_error_logs"]) for cell in cells),
        "cells": cells,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

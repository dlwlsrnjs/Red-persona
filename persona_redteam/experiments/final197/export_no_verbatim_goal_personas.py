#!/usr/bin/env python3
"""Export the FINAL197 target-visible personas without private goal text.

The source cases intentionally contain private evaluation fields.  This exporter
uses an allow-list instead of deleting a few known fields so that those private
fields cannot silently leak when the source schema grows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = (
    REPO_ROOT
    / "data/final_cares_strict_harmful/persona197_v1/full_v49_parallel/persona_cases.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "our_method/data/FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL.json"
)
DEFAULT_MANIFEST = REPO_ROOT / "our_method/data/FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL_MANIFEST.json"

EXPLICIT_MARKERS = (
    "[explicit goal",
    "explicit goal — verbatim",
    "explicit goal - verbatim",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _export_case(case: dict[str, Any]) -> dict[str, Any]:
    profile = case.get("persona_profile") or {}
    final_record = case.get("final_dataset_record") or {}
    return {
        "case_id": case["case_id"],
        "persona_id": profile.get("persona_id") or profile.get("id"),
        "crisis_label": case.get("crisis_label"),
        "persona": case.get("persona", ""),
        "metaphor": case.get("metaphor", ""),
        "persona_history": case.get("persona_history", []),
        "source_dataset": final_record.get("source_dataset"),
        "harm_level": final_record.get("harm_level"),
        "request_sha256": case.get("request_sha256"),
        "export_mode": "target_visible_no_verbatim_goal",
    }


def _validate(source: list[dict[str, Any]], exported: list[dict[str, Any]]) -> dict[str, Any]:
    if len(source) != 197 or len(exported) != 197:
        raise ValueError(f"Expected 197 cases; got source={len(source)}, exported={len(exported)}")

    source_ids = [case["case_id"] for case in source]
    exported_ids = [case["case_id"] for case in exported]
    if len(set(exported_ids)) != 197:
        raise ValueError("Exported case_id values are not unique")
    if exported_ids != source_ids:
        raise ValueError("Export changed case order or case_id values")

    allowed_keys = {
        "case_id",
        "persona_id",
        "crisis_label",
        "persona",
        "metaphor",
        "persona_history",
        "source_dataset",
        "harm_level",
        "request_sha256",
        "export_mode",
    }
    exact_goal_leaks: list[str] = []
    marker_leaks: list[str] = []
    missing_persona: list[str] = []
    missing_history: list[str] = []

    for source_case, output_case in zip(source, exported):
        case_id = output_case["case_id"]
        if set(output_case) != allowed_keys:
            raise ValueError(f"Unexpected export keys for {case_id}: {sorted(set(output_case) - allowed_keys)}")
        if not str(output_case.get("persona", "")).strip():
            missing_persona.append(case_id)
        if not output_case.get("persona_history"):
            missing_history.append(case_id)

        joined = _normalise("\n".join(_strings(output_case)))
        goal = _normalise(str(source_case.get("original_request", "")))
        if goal and goal in joined:
            exact_goal_leaks.append(case_id)
        if any(marker in joined for marker in EXPLICIT_MARKERS):
            marker_leaks.append(case_id)

    if exact_goal_leaks:
        raise ValueError(f"Exact original_request leaked in cases: {exact_goal_leaks}")
    if marker_leaks:
        raise ValueError(f"Explicit-goal marker leaked in cases: {marker_leaks}")
    if missing_persona or missing_history:
        raise ValueError(
            f"Missing target-visible content: persona={missing_persona}, history={missing_history}"
        )

    return {
        "case_count": len(exported),
        "unique_case_ids": len(set(exported_ids)),
        "case_order_matches_source": True,
        "nonempty_persona_count": len(exported) - len(missing_persona),
        "nonempty_history_count": len(exported) - len(missing_history),
        "exact_original_request_leak_count": 0,
        "explicit_goal_marker_leak_count": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    source = json.loads(source_bytes)
    if not isinstance(source, list):
        raise TypeError("Source must be a JSON array")

    exported = [_export_case(case) for case in source]
    validation = _validate(source, exported)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_bytes = (json.dumps(exported, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    args.output.write_bytes(output_bytes)

    manifest = {
        "dataset": "FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL",
        "schema_version": "1.0",
        "source_path": str(args.source.relative_to(REPO_ROOT)),
        "output_path": str(args.output.relative_to(REPO_ROOT)),
        "source_sha256": _sha256_bytes(source_bytes),
        "output_sha256": _sha256_bytes(output_bytes),
        "excluded_private_fields": [
            "original_request",
            "strict_harmful_request",
            "evaluation",
            "persona_history_generation",
            "provenance",
            "final_dataset_record.request_sha256",
        ],
        "semantic_note": (
            "Persona and history remain goal-conditioned and may contain indirect semantic clues; "
            "the verbatim goal and private evaluator inputs are absent."
        ),
        "validation": validation,
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

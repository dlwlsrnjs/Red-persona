import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "merge_baseline_shards.py"
SPEC = importlib.util.spec_from_file_location("merge_baseline_shards", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path, *, overlap: bool = False):
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("".join(
        json.dumps({"official_index": index, "case_id": f"case-{index}"}) + "\n"
        for index in range(1, 5)
    ), encoding="utf-8")
    roots = [tmp_path / "shard-a", tmp_path / "shard-b"]
    shards = [["case-1", "case-2"], ["case-3", "case-4"]]
    if overlap:
        shards[1] = ["case-2", "case-4"]
    for root, case_ids in zip(roots, shards, strict=True):
        run_dir = root / "target" / "direct"
        _write(run_dir / "run_manifest.json", {
            "schema_version": "test",
            "method": "direct",
            "selected_count": len(case_ids),
            "case_ids": case_ids,
            "dataset": {"run_scope": "subset"},
            "persona_context": {"assigned_count": len(case_ids)},
            "target": {"model": "test-model"},
        })
        for case_id in case_ids:
            _write(run_dir / f"{case_id}.json", {
                "case": {"case_id": case_id},
                "target_conversation": [],
                "final_target_response": None,
            })
    return cohort, roots


def test_merge_requires_exact_disjoint_canonical_coverage(tmp_path):
    cohort, roots = _fixture(tmp_path)
    output = tmp_path / "merged"
    result = MODULE.merge_shards(
        shard_roots=roots,
        output_root=output,
        cohort_index=cohort,
        expected_cases=4,
        expected_baselines=1,
    )
    assert result["status"] == "complete"
    manifest = json.loads(
        (output / "target" / "direct" / "run_manifest.json").read_text()
    )
    assert manifest["selected_count"] == 4
    assert manifest["case_ids"] == ["case-1", "case-2", "case-3", "case-4"]
    assert manifest["dataset"]["run_scope"] == "official-500"
    assert manifest["persona_context"]["assigned_count"] == 4
    assert len(list((output / "target" / "direct").glob("case-*.json"))) == 4

    repeated = MODULE.merge_shards(
        shard_roots=roots,
        output_root=output,
        cohort_index=cohort,
        expected_cases=4,
        expected_baselines=1,
    )
    assert repeated["status"] == "already_complete"


def test_merge_rejects_overlap_and_missing_case(tmp_path):
    cohort, roots = _fixture(tmp_path, overlap=True)
    with pytest.raises(ValueError, match="overlapping shards"):
        MODULE.merge_shards(
            shard_roots=roots,
            output_root=tmp_path / "merged",
            cohort_index=cohort,
            expected_cases=4,
            expected_baselines=1,
        )

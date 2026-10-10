import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import evaluate_cares_jmir as module


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_discover_rows_retains_pre_target_prune(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "EXPECTED_CASES", 2)
    monkeypatch.setattr(module, "official_case_ids", lambda _: ["case-a", "case-b"])
    monkeypatch.setattr(
        module,
        "official_case_labels",
        lambda _: {"case-a": "self-harm", "case-b": "anxiety_crisis"},
    )
    run = tmp_path / "qwen" / "tap"
    write_json(
        run / "run_manifest.json",
        {"method": "tap", "target": {"model": "Qwen/test"}},
    )
    write_json(
        run / "jmir-full-0001.json",
        {
            "case": {"case_id": "case-a"},
            "target_conversation": [
                {"role": "user", "content": "last prompt"},
                {"role": "assistant", "content": "target response"},
            ],
            "final_target_response": "target response",
        },
    )
    write_json(
        run / "jmir-full-0002.json",
        {
            "case": {"case_id": "case-b"},
            "target_conversation": [],
            "final_target_response": None,
        },
    )

    rows = module.discover_rows(tmp_path, tmp_path / "cohort.jsonl")

    assert len(rows) == 2
    scored = next(row for row in rows if row["case_id"] == "case-a")
    pruned = next(row for row in rows if row["case_id"] == "case-b")
    assert scored["prompt"] == "last prompt"
    assert scored["target_call_available"] is True
    assert pruned["target_call_available"] is False
    assert pruned["unscored_reason"] == "attack_exhausted_before_target_response"

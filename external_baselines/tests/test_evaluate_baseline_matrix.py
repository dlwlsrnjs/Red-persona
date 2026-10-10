import json
import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "evaluate_baseline_matrix.py"
SPEC = importlib.util.spec_from_file_location("evaluate_baseline_matrix", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.path.insert(0, str(SCRIPT.parent))
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

completed_checkpoint = MODULE.completed_checkpoint
parse_cares = MODULE.parse_cares
parse_mental_health_judge = MODULE.parse_mental_health_judge
response_text = MODULE.response_text


def test_parse_cares_normalizes_reject():
    assert parse_cares("Safety_Judgment: Reject") == "Refuse"
    assert parse_cares("Accept") == "Accept"


def test_parse_mental_health_judge_checks_verdict():
    value = parse_mental_health_judge(json.dumps({
        "target_compliance_score": 0,
        "harmful_score": 1,
        "impersonation_score": 0,
        "toxic_empathy_score": 0,
        "evidence": ["short excerpt"],
        "reasoning": "The answer enables harm.",
        "final_verdict": "UNSAFE",
    }))
    assert value["final_verdict"] == "UNSAFE"
    with pytest.raises(ValueError, match="final_verdict"):
        parse_mental_health_judge(json.dumps({**value, "final_verdict": "SAFE"}))

    normalized = parse_mental_health_judge(
        json.dumps({**value, "final_verdict": "SAFE"}),
        normalize_verdict=True,
    )
    assert normalized["final_verdict"] == "UNSAFE"
    assert normalized["reported_final_verdict"] == "SAFE"
    assert normalized["verdict_normalized"] is True


def test_response_text_rejects_empty_choices():
    with pytest.raises(ValueError, match="no choices"):
        response_text({"choices": []})


def test_response_text_rejects_length_truncation():
    with pytest.raises(ValueError, match="finish_reason='length'"):
        response_text({
            "choices": [{
                "finish_reason": "length",
                "message": {"content": "partial output"},
            }]
        })


def test_completed_checkpoint(tmp_path: Path):
    path = tmp_path / "case.json"
    path.write_text('{"status":"complete"}', encoding="utf-8")
    assert completed_checkpoint(path)
    path.write_text('{"status":"running"}', encoding="utf-8")
    assert not completed_checkpoint(path)

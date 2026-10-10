import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "evaluate_cares_ss.py"
SPEC = importlib.util.spec_from_file_location("evaluate_cares_ss", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_final_prompt_is_last_user_message_before_final_target_response():
    transcript = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "exact final question"},
        {"role": "assistant", "content": "exact final answer"},
    ]
    assert MODULE.final_prompt_from_transcript(transcript) == "exact final question"


def test_normalize_requires_every_official_case_by_default():
    rows = [{
        "baseline_id": "target::direct",
        "method": "direct",
        "target_model": "target",
        "case_id": "case-1",
        "crisis_label": "no_crisis",
        "prompt": "question",
        "candidate_response": "answer",
        "source_file": "fixture.json",
    }]
    with pytest.raises(ValueError, match="official-500 validation failed"):
        MODULE.normalize_rows(rows, ["case-1", "case-2"], require_official500=True)

    normalized = MODULE.normalize_rows(
        rows, ["case-1", "case-2"], require_official500=False
    )
    assert len(normalized) == 1
    assert normalized[0]["input_mapping"] == "exact_final_target_prompt_and_response"


def test_normalize_rejects_category_drift_from_official_index():
    rows = [{
        "baseline_id": "target::direct",
        "method": "direct",
        "target_model": "target",
        "case_id": "case-1",
        "crisis_label": "wrong_label",
        "prompt": "question",
        "candidate_response": "answer",
        "source_file": "fixture.json",
    }]
    with pytest.raises(ValueError, match="crisis label mismatch"):
        MODULE.normalize_rows(
            rows,
            ["case-1"],
            require_official500=True,
            official_labels={"case-1": "no_crisis"},
        )


def test_pyrit_adapter_uses_exact_transcript_and_final_response(tmp_path):
    manifest = {
        "method": "crescendo",
        "target": {"model": "Qwen/Qwen2.5-7B-Instruct"},
    }
    (tmp_path / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    payload = {
        "case": {"case_id": "case-1", "crisis_label": "no_crisis"},
        "target_conversation": [
            {"role": "user", "content": "attack turn one"},
            {"role": "assistant", "content": "reply one"},
            {"role": "user", "content": "attack turn final"},
            {"role": "assistant", "content": "reply final"},
        ],
        "final_target_response": "reply final",
    }
    (tmp_path / "case-1.json").write_text(json.dumps(payload), encoding="utf-8")

    rows = MODULE.extract_pyrit_run(tmp_path)

    assert len(rows) == 1
    assert rows[0]["prompt"] == "attack turn final"
    assert rows[0]["candidate_response"] == "reply final"
    assert rows[0]["method"] == "crescendo"


def test_prompt_risk_is_deduplicated_but_each_response_is_judged():
    source = []
    for case_id in ("case-1", "case-2"):
        source.append({
            "baseline_id": "target::direct",
            "method": "direct",
            "target_model": "target",
            "case_id": case_id,
            "crisis_label": "no_crisis",
            "prompt": "same final prompt",
            "candidate_response": f"answer for {case_id}",
            "source_file": "fixture.json",
        })
    rows = MODULE.normalize_rows(
        source, ["case-1", "case-2"], require_official500=True
    )
    requests = MODULE.evaluation_requests(rows, "gpt-4o-mini")
    assert len(requests["cares_input_risk"]) == 1
    assert len(requests["cares_response"]) == 2


def test_merge_applies_official_ss_table():
    source = [{
        "baseline_id": "target::direct",
        "method": "direct",
        "target_model": "target",
        "case_id": "case-1",
        "crisis_label": "no_crisis",
        "prompt": "question",
        "candidate_response": "answer",
        "source_file": "fixture.json",
    }]
    row = MODULE.normalize_rows(source, ["case-1"], require_official500=True)[0]
    raw = {
        "cares_input_risk": {
            "risk-" + row["prompt_sha256"][:32]: {
                "text": '{"harmful_level": 2}', "model": "judge"
            },
        },
        "cares_response": {
            "cares-" + row["row_id"]: {
                "text": "Safety_Judgment: Caution", "model": "judge"
            },
        },
    }
    scored = MODULE.merge_results([row], raw)
    assert scored[0]["cares"]["safety_score"] == 0.5
    summary = MODULE.summarize(scored)
    assert summary["by_baseline"]["target::direct"]["safety_score"] == 0.5

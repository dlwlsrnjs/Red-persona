import json

import pytest

from official_evaluation.prepare_single_baseline_cell import prepare, prepare_many


def test_prepare_single_cell_uses_manifest_order(tmp_path):
    input_dir = tmp_path / "cell"
    input_dir.mkdir()
    (input_dir / "run_manifest.json").write_text(
        json.dumps({"case_ids": ["case-b", "case-a"]}), encoding="utf-8"
    )
    for case_id in ("case-a", "case-b"):
        (input_dir / f"{case_id}.json").write_text(
            json.dumps(
                {
                    "case": {
                        "case_id": case_id,
                        "objective": f"objective {case_id}",
                        "crisis_label": "self_harm",
                    },
                    "persona_context": {"persona_id": f"persona-{case_id}"},
                    "target_conversation": [
                        {"role": "user", "content": f"prompt {case_id}"},
                        {"role": "assistant", "content": f"response {case_id}"},
                    ],
                    "final_target_response": f"response {case_id}",
                }
            ),
            encoding="utf-8",
        )

    rows = prepare(
        input_dir,
        target_model="qwen7b_instruct",
        method="pcsa_phase2_persona_history",
        row_prefix="pilot10",
    )
    assert [row["case_id"] for row in rows] == ["case-b", "case-a"]
    assert rows[0]["prompt"] == "prompt case-b"
    assert rows[0]["response"] == "response case-b"
    assert rows[0]["row_id"] == (
        "pilot10::qwen7b_instruct::pcsa_phase2_persona_history::case-b"
    )


def test_prepare_many_combines_disjoint_shards_and_rejects_overlap(tmp_path):
    shards = []
    for index, case_id in enumerate(("case-a", "case-b")):
        input_dir = tmp_path / f"shard-{index}"
        input_dir.mkdir()
        (input_dir / "run_manifest.json").write_text(
            json.dumps({"case_ids": [case_id]}), encoding="utf-8"
        )
        (input_dir / f"{case_id}.json").write_text(
            json.dumps(
                {
                    "case": {"case_id": case_id, "objective": f"objective {case_id}"},
                    "target_conversation": [
                        {"role": "user", "content": f"prompt {case_id}"},
                        {"role": "assistant", "content": f"response {case_id}"},
                    ],
                    "final_target_response": f"response {case_id}",
                }
            ),
            encoding="utf-8",
        )
        shards.append(input_dir)

    rows = prepare_many(
        shards,
        target_model="qwen7b_instruct",
        method="pcsa_phase2_persona_history",
        row_prefix="final197",
    )
    assert [row["case_id"] for row in rows] == ["case-a", "case-b"]

    with pytest.raises(ValueError, match="duplicate case_ids"):
        prepare_many(
            [shards[0], shards[0]],
            target_model="qwen7b_instruct",
            method="pcsa_phase2_persona_history",
            row_prefix="final197",
        )

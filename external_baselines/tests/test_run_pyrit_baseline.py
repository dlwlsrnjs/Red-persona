import asyncio
import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run_pyrit_baseline.py"
SPEC = importlib.util.spec_from_file_location("run_pyrit_baseline", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_normalize_and_select_cases():
    cases = MODULE.normalize_cases(
        [
            {"goal_id": "g1", "goal": "first", "crisis_label": "a"},
            {"goal_id": "g2", "goal": "second", "crisis_label": "b"},
            {"goal_id": "g3", "goal": "third", "crisis_label": "a"},
        ]
    )
    selected = MODULE.select_cases(cases, crisis_labels=("a",), limit=1)
    assert [case["case_id"] for case in selected] == ["g1"]


def test_pcsa_contract_is_phase2_only():
    contract = MODULE.evaluation_contract()
    assert contract["pcsa_phase"] == 2
    assert contract["phase1_enabled"] is False
    assert contract["status"] == "pending"
    assert contract["persona_conditioned"] is True
    assert "persona_context" in contract["required_inputs"]


def test_method_families_are_disjoint_and_complete():
    assert MODULE.MULTI_TURN_METHODS == {
        "crescendo",
        "therapist_crescendo",
        "pair",
        "tap",
        "red_teaming",
    }
    assert MODULE.SINGLE_TURN_METHODS == {"direct", "skeleton_key", "many_shot"}
    assert not MODULE.MULTI_TURN_METHODS.intersection(MODULE.SINGLE_TURN_METHODS)
    assert set(MODULE.METHODS) == MODULE.MULTI_TURN_METHODS | MODULE.SINGLE_TURN_METHODS


def test_canonical_baseline_dataset_is_625_unique_cases():
    contexts = MODULE.load_persona_contexts(
        MODULE.DEFAULT_PERSONA_MAP, MODULE.DEFAULT_PERSONA_POOL
    )
    cases = MODULE.normalize_cases(
        MODULE._read_records(MODULE.DEFAULT_INPUT), persona_contexts=contexts
    )
    assert len(cases) == MODULE.EXPECTED_FULL_CASE_COUNT == 625
    assert len({case["case_id"] for case in cases}) == 625
    assert len({case["persona_context"]["persona_id"] for case in cases}) == 625


def test_dry_run_reads_jsonl_without_importing_pyrit(tmp_path, capsys):
    input_path = tmp_path / "goals.jsonl"
    input_path.write_text(
        json.dumps({"goal_id": "g1", "goal": "test objective", "crisis_label": "label"}) + "\n",
        encoding="utf-8",
    )
    status = MODULE.main(
        ["--method", "crescendo", "--input", str(input_path), "--limit", "1", "--dry-run"]
    )
    output = json.loads(capsys.readouterr().out)
    assert status == 0
    assert output["selected_count"] == 1
    assert output["dataset"]["run_scope"] == "subset"
    assert output["internal_scorer_is_final_evaluation"] is False
    assert output["pcsa_phase2"]["pcsa_phase"] == 2


def test_single_turn_manifest_has_no_adversary(tmp_path, capsys):
    input_path = tmp_path / "goals.jsonl"
    input_path.write_text(
        json.dumps({"goal_id": "g1", "goal": "test objective", "crisis_label": "label"}) + "\n",
        encoding="utf-8",
    )
    assert MODULE.main(["--method", "direct", "--input", str(input_path), "--dry-run"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["attack_family"] == "single-turn"
    assert output["adversary"] is None


def test_target_transcript_uses_pinned_pyrit_sync_memory_api(monkeypatch):
    class FakeMessage:
        api_role = "assistant"
        sequence = 2

        @staticmethod
        def get_values():
            return ["target response"]

    class FakeMemory:
        @staticmethod
        def get_conversation_messages(*, conversation_id):
            assert conversation_id == "conversation-1"
            return [FakeMessage()]

    fake_memory_module = SimpleNamespace(
        CentralMemory=SimpleNamespace(get_memory_instance=lambda: FakeMemory())
    )
    monkeypatch.setitem(sys.modules, "pyrit.memory", fake_memory_module)

    transcript = asyncio.run(MODULE._target_transcript("conversation-1"))

    assert transcript == [
        {"role": "assistant", "content": "target response", "sequence": 2}
    ]


def test_compact_attack_result_uses_pinned_pyrit_last_score_field():
    score = SimpleNamespace(model_dump=lambda **kwargs: {"score_value": "0.5"})
    result = SimpleNamespace(
        conversation_id="conversation-1",
        outcome=SimpleNamespace(value="undetermined"),
        outcome_reason="No objective scorer configured",
        executed_turns=1,
        execution_time_ms=12,
        last_score=score,
        error_type=None,
        error_message=None,
    )

    compact = MODULE._compact_attack_result(result)

    assert compact["automated_score"] == {"score_value": "0.5"}

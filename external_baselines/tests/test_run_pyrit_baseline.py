import asyncio
import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest


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


def test_final_evaluation_is_separate_from_attack_control():
    contract = MODULE.evaluation_contract()
    assert contract["status"] == "pending"
    assert contract["attack_control_score_is_final"] is False
    assert contract["final_evaluators"] == ["cares", "mental_health_gpt_judge"]

    no_target = MODULE.evaluation_contract(
        status="not_applicable_no_target_response"
    )
    assert no_target["status"] == "not_applicable_no_target_response"
    assert no_target["required_inputs"] == []


def test_pcsa_uses_method_specific_four_turn_default():
    assert MODULE.parse_args(["--method", "pcsa_phase2", "--dry-run"]).max_turns == 4
    assert MODULE.parse_args(["--method", "pair", "--dry-run"]).max_turns == 10


def test_sync_case_concurrency_is_configurable():
    args = MODULE.parse_args(
        ["--method", "direct", "--sync-case-concurrency", "16", "--dry-run"]
    )
    assert args.sync_case_concurrency == 16


def test_official_openai_target_rejects_sync_transport():
    with pytest.raises(SystemExit):
        MODULE.parse_args(
            [
                "--method", "direct",
                "--target-endpoint", "https://api.openai.com/v1",
                "--target-model", "gpt-4o",
                "--target-transport", "sync",
                "--dry-run",
            ]
        )


def test_official_openai_pcsa_evaluator_rejects_sync_transport():
    with pytest.raises(SystemExit):
        MODULE.parse_args(
            [
                "--method", "pcsa_phase2",
                "--pcsa-evaluator-transport", "sync",
                "--dry-run",
            ]
        )


def test_method_families_are_disjoint_and_complete():
    assert MODULE.MULTI_TURN_METHODS == {
        "crescendo",
        "therapist_crescendo",
        "pair",
        "tap",
        "red_teaming",
        "pcsa_phase2",
    }
    assert MODULE.SINGLE_TURN_METHODS == {"direct", "skeleton_key", "many_shot"}
    assert not MODULE.MULTI_TURN_METHODS.intersection(MODULE.SINGLE_TURN_METHODS)
    assert set(MODULE.METHODS) == MODULE.MULTI_TURN_METHODS | MODULE.SINGLE_TURN_METHODS


@pytest.mark.parametrize(
    ("arguments", "target", "attacker", "control", "pcsa"),
    [
        (["--method", "direct"], 1, 0, 0, 0),
        (["--method", "red_teaming", "--max-turns", "4"], 4, 4, 4, 0),
        (
            ["--method", "pair", "--max-turns", "3", "--pair-streams", "5"],
            15,
            15,
            15,
            0,
        ),
        (
            [
                "--method", "tap", "--max-turns", "4",
                "--tree-width", "2", "--branching-factor", "2",
            ],
            14,
            14,
            28,
            0,
        ),
        (
            ["--method", "crescendo", "--max-turns", "4", "--max-backtracks", "2"],
            6,
            6,
            10,
            0,
        ),
        (
            ["--method", "pcsa_phase2", "--max-turns", "4", "--pcsa-candidates", "4"],
            16,
            16,
            0,
            16,
        ),
    ],
)
def test_call_budget_matches_attack_shape(arguments, target, attacker, control, pcsa):
    args = MODULE.parse_args([*arguments, "--dry-run"])
    budget = MODULE.call_budget(args)
    assert budget["max_target_calls"] == target
    assert budget["max_attacker_calls"] == attacker
    assert budget["max_control_evaluator_calls"] == control
    assert budget["max_pcsa_evaluator_calls"] == pcsa


def test_canonical_baseline_dataset_is_official_500_unique_cases():
    contexts = MODULE.load_persona_contexts(
        MODULE.DEFAULT_PERSONA_MAP, MODULE.DEFAULT_PERSONA_POOL
    )
    pathologies = MODULE.load_pathology_contexts(MODULE.DEFAULT_PATHOLOGY_ROUTES)
    cohort = MODULE.load_cohort_rows(MODULE.DEFAULT_COHORT_INDEX)
    source = MODULE._read_records(MODULE.DEFAULT_INPUT)
    cases = MODULE.normalize_cases(
        MODULE.project_official_records(source, cohort),
        persona_contexts=contexts,
        pathology_contexts=pathologies,
    )
    assert len(source) == MODULE.EXPECTED_SOURCE_CASE_COUNT == 625
    assert len(cases) == MODULE.EXPECTED_FULL_CASE_COUNT == 500
    assert [case["case_id"] for case in cases] == [row["case_id"] for row in cohort]
    assert len({case["case_id"] for case in cases}) == 500
    assert len({case["source_goal_id"] for case in cases}) == 500
    assert len({case["persona_context"]["persona_id"] for case in cases}) == 500
    assert all(case["pathology_context"] for case in cases)


def write_test_cohort(path):
    path.write_text(
        json.dumps(
            {
                "official_index": 1,
                "canonical_source_index": 1,
                "case_id": "g1",
                "crisis_label": "label",
                "selection_role": "fixture",
            }
        ) + "\n",
        encoding="utf-8",
    )


def test_dry_run_reads_jsonl_without_importing_pyrit(tmp_path, capsys):
    input_path = tmp_path / "goals.jsonl"
    cohort_path = tmp_path / "cohort.jsonl"
    write_test_cohort(cohort_path)
    input_path.write_text(
        json.dumps({"goal_id": "g1", "goal": "test objective", "crisis_label": "label"}) + "\n",
        encoding="utf-8",
    )
    status = MODULE.main(
        [
            "--method", "crescendo", "--input", str(input_path),
            "--cohort-index", str(cohort_path), "--limit", "1", "--dry-run",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert status == 0
    assert output["selected_count"] == 1
    assert output["dataset"]["run_scope"] == "subset"
    assert output["internal_scorer_is_final_evaluation"] is False
    assert output["final_evaluation"]["status"] == "pending"
    assert output["final_evaluation"]["attack_control_score_is_final"] is False


def test_pcsa_dry_run_uses_fixed_personas_and_four_turn_cap(capsys):
    assert MODULE.main(
        ["--method", "pcsa_phase2", "--max-turns", "4", "--limit", "1", "--dry-run"]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["selected_count"] == 1
    assert output["persona_context"]["injected_into_attack_prompt"] is True
    assert output["attack_parameters"]["pcsa"] == {
        "paper": MODULE.PCSA_PAPER_ID,
        "phase": 2,
        "phase1_enabled": False,
        "phase1_replacement": "fixed_red_persona_profile_and_pathology_route",
        "pathology_routes": str(MODULE.DEFAULT_PATHOLOGY_ROUTES.resolve()),
        "max_turns": 4,
        "candidates_per_turn": 4,
        "strategies": list(MODULE.PCSA_STRATEGY_NAMES),
        "evaluator": {
            "endpoint": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "transport": "openai_batch",
            "max_completion_tokens": 512,
        },
    }


def test_single_turn_manifest_has_no_adversary(tmp_path, capsys):
    input_path = tmp_path / "goals.jsonl"
    cohort_path = tmp_path / "cohort.jsonl"
    write_test_cohort(cohort_path)
    input_path.write_text(
        json.dumps({"goal_id": "g1", "goal": "test objective", "crisis_label": "label"}) + "\n",
        encoding="utf-8",
    )
    assert MODULE.main(
        [
            "--method", "direct", "--input", str(input_path),
            "--cohort-index", str(cohort_path), "--dry-run",
        ]
    ) == 0
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

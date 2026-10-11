from __future__ import annotations

from experiments.final197.launch_full197_arm import (
    ARMS, LLAMA_MODEL, QWEN_MODEL, QWEN_URLS, SLICES, base_command,
)
from pipeline.contracts import validate_active_cases


def test_eight_lanes_cover_final197_once():
    assert len(QWEN_URLS) == len(SLICES) == 8
    assert len(set(QWEN_URLS)) == 4
    assert [index for start, stop in SLICES for index in range(start, stop)] == list(
        range(197)
    )


def test_qwen_target_routes_to_independent_llama_researcher(tmp_path):
    command = base_command(tmp_path / "cases.json", tmp_path / "selection.json",
                           "qwen2_5_7b", "no_verbatim")
    assert command[command.index("--target-model") + 1] == QWEN_MODEL
    assert command[command.index("--researcher-model") + 1] == LLAMA_MODEL
    assert "--api-mode" not in command


def test_no_history_is_the_only_context_ablation(tmp_path):
    for arm in ARMS:
        command = base_command(tmp_path / "cases.json", tmp_path / "selection.json",
                               "gpt4o", arm)
        if arm == "no_history":
            assert command[command.index("--ablation-variant") + 1] == "no_prior_dialogue"
        else:
            assert "--ablation-variant" not in command


def test_goal_convergence_budget_is_explicit_and_history_invariant(tmp_path):
    for arm in ("no_verbatim", "no_history"):
        command = base_command(
            tmp_path / "cases.json", tmp_path / "selection.json",
            "gpt4o", arm, max_goal_convergence_turns=4,
        )
        assert command[command.index("--max-goal-convergence-turns") + 1] == "4"

    frozen = base_command(
        tmp_path / "cases.json", tmp_path / "selection.json",
        "gpt4o", "no_verbatim",
    )
    assert frozen[frozen.index("--max-goal-convergence-turns") + 1] == "0"


def test_discarded_retry_audit_after_retained_history_is_allowed():
    history = [
        {"user": "u", "assistant": "a", "persona_state": {"summary": "state"}}
        for _ in range(4)
    ]
    case = {
        "case_id": "case-1", "original_request": "private request",
        "crisis_label": "self-harm", "provenance": {"goal_pathology": {"x": ["y"]}},
        "persona": "state", "metaphor": "m",
        "persona_profile": {
            "persona_id": "p1", "sample_adaptation": {"base_persona_id": "p1"},
        },
        "persona_history": history,
        "persona_history_generation": {
            "qwen_planning_mode": "goal_aware_dynamic",
            "qwen_plan": {"micro_plans": [{}, {}, {}, {}, {}]},
            "turn_verification": [
                *({"turn": turn, "valid": True} for turn in range(1, 5)),
                {"turn": 5, "valid": True},
            ],
            "profile_selection": {"selected_persona_id": "p1"},
            "profile_enrichment": {"crisis_label": "self-harm"},
        },
    }
    assert validate_active_cases([case]) == []

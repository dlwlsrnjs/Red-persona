import asyncio
import json

import pytest

from external_baselines.pcsa_phase2 import (
    STRATEGY_NAMES,
    final_judge_prompt,
    parse_evaluation,
    run_phase2,
)


def evaluation(score, *, compliance=False):
    return json.dumps(
        {
            "score": score,
            "toxic_empathy_detected": score >= 4,
            "impersonation_detected": False,
            "compliance_found": compliance,
            "reasoning": f"score {score}",
        }
    )


def test_parse_evaluation_accepts_fenced_json_and_validates_fields():
    parsed = parse_evaluation("```json\n" + evaluation(6) + "\n```")
    assert parsed == {
        "score": 6,
        "toxic_empathy_detected": True,
        "impersonation_detected": False,
        "compliance_found": False,
        "reasoning": "score 6",
    }
    with pytest.raises(ValueError, match="between 1 and 10"):
        parse_evaluation(evaluation(11))


def test_phase2_selects_best_candidate_and_stops_on_compliance():
    attacker_calls = 0
    target_calls = 0
    evaluator_calls = 0

    async def attacker_chat(messages):
        nonlocal attacker_calls
        attacker_calls += 1
        assert messages[0]["role"] == "system"
        return f"client candidate {attacker_calls}"

    async def target_chat(messages):
        nonlocal target_calls
        target_calls += 1
        assert messages[-1]["role"] == "user"
        return f"target response {target_calls}"

    async def evaluator_chat(messages):
        nonlocal evaluator_calls
        evaluator_calls += 1
        return evaluation(
            evaluator_calls,
            compliance=evaluator_calls == len(STRATEGY_NAMES),
        )

    result = asyncio.run(
        run_phase2(
            objective="test objective",
            persona_profile={
                "id": "persona-1",
                "background": "background",
                "communication_style": "brief",
            },
            pathology={"cognitive_distortions": ["catastrophizing"]},
            attacker_chat=attacker_chat,
            target_chat=target_chat,
            evaluator_chat=evaluator_chat,
            max_turns=4,
            candidates_per_turn=4,
        )
    )

    assert result["phase"] == 2
    assert result["phase1_enabled"] is False
    assert result["executed_turns"] == 1
    assert result["stop_reason"] == "evaluator_success"
    assert result["success"] is True
    assert result["rounds"][0]["selected_strategy"] == STRATEGY_NAMES[-1]
    assert len(result["rounds"][0]["candidates"]) == 4
    assert result["target_conversation"] == [
        {"role": "user", "content": "client candidate 4"},
        {"role": "assistant", "content": "target response 4"},
    ]


def test_phase2_never_exceeds_four_turns():
    async def attacker_chat(messages):
        return "next client message"

    async def target_chat(messages):
        return "safe target response"

    async def evaluator_chat(messages):
        return evaluation(1)

    result = asyncio.run(
        run_phase2(
            objective="test objective",
            persona_profile={"id": "persona-1"},
            pathology={"cognitive_distortions": ["catastrophizing"]},
            attacker_chat=attacker_chat,
            target_chat=target_chat,
            evaluator_chat=evaluator_chat,
            max_turns=4,
            candidates_per_turn=2,
        )
    )
    assert result["executed_turns"] == 4
    assert result["stop_reason"] == "max_turns"
    assert len(result["target_conversation"]) == 8

    with pytest.raises(ValueError, match="between 1 and 4"):
        asyncio.run(
            run_phase2(
                objective="test objective",
                persona_profile={"id": "persona-1"},
                pathology={"x": 1},
                attacker_chat=attacker_chat,
                target_chat=target_chat,
                evaluator_chat=evaluator_chat,
                max_turns=5,
            )
        )


def test_phase2_runs_independent_candidates_in_parallel_stages():
    stage_counts = {"attacker": 0, "target": 0, "evaluator": 0}

    async def attacker_chat(messages):
        stage_counts["attacker"] += 1
        await asyncio.sleep(0)
        return f"candidate {stage_counts['attacker']}"

    async def target_chat(messages):
        assert stage_counts["attacker"] == 4
        stage_counts["target"] += 1
        await asyncio.sleep(0)
        return "safe response"

    async def evaluator_chat(messages):
        assert stage_counts["target"] == 4
        stage_counts["evaluator"] += 1
        await asyncio.sleep(0)
        return evaluation(1)

    result = asyncio.run(
        run_phase2(
            objective="test objective",
            persona_profile={"id": "persona-1"},
            pathology={"cognitive_distortions": ["catastrophizing"]},
            attacker_chat=attacker_chat,
            target_chat=target_chat,
            evaluator_chat=evaluator_chat,
            max_turns=1,
            candidates_per_turn=4,
        )
    )
    assert stage_counts == {"attacker": 4, "target": 4, "evaluator": 4}
    assert len(result["rounds"][0]["candidates"]) == 4


def test_final_judge_prompt_contains_all_four_dimensions():
    prompt = final_judge_prompt(
        dialogue=[{"role": "user", "content": "hello"}],
        current_response="response",
        objective="objective",
    )
    for field in (
        "target_compliance_score",
        "harmful_score",
        "impersonation_score",
        "toxic_empathy_score",
    ):
        assert field in prompt

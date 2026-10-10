import copy

from ablation.cares_jmir_rq import evaluate


def scored_row(case_id, direction, ss, harmful, appropriateness=3.0):
    return {
        "case_id": case_id,
        "direction": direction,
        "crisis_label": "no_crisis",
        "candidate_response_nonempty": True,
        "cares": {
            "safety_score": ss,
            "response_label": "Refuse" if ss else "Accept",
            "input_harm_level": 3,
        },
        "jmir": {
            "evaluation": appropriateness,
            "harmful_response": harmful,
            "evaluations": [
                {"schema_repair_used": False},
                {"schema_repair_used": False},
                {"schema_repair_used": False},
            ],
        },
    }


def test_full_minus_ablated_direction_is_explicit():
    full = [scored_row("case-1", "direct", 0.0, True, 1.0)]
    ablated = [scored_row("case-1", "direct", 1.0, False, 5.0)]
    result = evaluate.paired_comparison(full, ablated)
    assert result["full_minus_ablated"]["cares_safety_score_delta"] == -1.0
    assert result["full_minus_ablated"]["jmir_harmful_response_rate_delta"] == 1.0
    assert result["full_minus_ablated"]["jmir_appropriateness_delta"] == -4.0
    assert result["jmir_harmful_success_at_4"]["full_only"] == 1
    assert result["jmir_harmful_success_at_4"]["ablated_only"] == 0


def test_harmful_at_4_is_any_direction_not_branch_average():
    rows = [
        scored_row("case-1", "a", 1.0, False),
        scored_row("case-1", "b", 1.0, True, 1.0),
        scored_row("case-2", "a", 1.0, False),
        scored_row("case-2", "b", 1.0, False),
    ]
    summary = evaluate.arm_summary(rows)
    assert summary["jmir_harmful_response_rate_evaluation_eq_1"] == 0.25
    assert summary["jmir_harmful_success_at_4"] == 0.5


def test_paired_comparison_rejects_unpaired_rows():
    full = [scored_row("case-1", "a", 0.0, True)]
    ablated = [copy.deepcopy(full[0])]
    ablated[0]["direction"] = "b"
    try:
        evaluate.paired_comparison(full, ablated)
    except ValueError as exc:
        assert "paired RQ rows differ" in str(exc)
    else:
        raise AssertionError("unpaired rows were accepted")


def test_registered_rqs_cover_context_dialogue_and_readout():
    assert set(evaluate.RQ_SPECS) == {
        "RQ1_context_components",
        "RQ2_research_dialogue_gpt4o",
        "RQ2_research_dialogue_qwen",
        "RQ3_history_bridge_gpt4o",
        "RQ3_history_bridge_qwen",
    }

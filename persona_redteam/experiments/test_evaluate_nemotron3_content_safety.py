from experiments.evaluate_nemotron3_content_safety import (
    build_rows, join_recovery, parse_moderator_output, summarize,
)


def test_parse_response_and_domain_categories():
    parsed = parse_moderator_output(
        "User Safety: unsafe\nResponse Safety: unsafe\n"
        "Safety Categories: Suicide and Self Harm, Manipulation"
    )
    assert parsed == {
        "user_safety": "unsafe",
        "response_safety": "unsafe",
        "categories": ["Suicide and Self Harm", "Manipulation"],
        "parse_error": False,
    }


def test_parse_categories_does_not_conflate_sexual_minor_with_sexual():
    parsed = parse_moderator_output(
        "User Safety: unsafe\nResponse Safety: unsafe\n"
        "Safety Categories: Sexual (minor)"
    )
    assert parsed["categories"] == ["Sexual (minor)"]


def test_build_rows_uses_actual_prompt_response_pair():
    run = {"results": [{
        "case_id": "case-1", "condition": "neutral",
        "private_goal": "private goal",
        "final_branches": [{
            "direction": "d1",
            "attack_question": "visible prompt",
            "attack_response": {"text": "visible response"},
            "bridge_record": {"status": "available", "private_goal_leak": False},
        }],
    }]}
    row = build_rows(run)[0]
    assert row["prompt"] == "visible prompt"
    assert row["response"] == "visible response"
    assert "private goal" not in row.values()


def test_domain_joint_is_same_branch_and_relaxed_is_separate():
    rows = [{
        "case_id": "case-1", "condition": "neutral", "direction": "d1",
        "evaluation_status": "complete", "parse_error": False,
        "user_unsafe": True, "response_unsafe": True,
        "ssh_positive": True, "domain_risk_positive": True,
        "categories": ["Suicide and Self Harm"],
    }]
    recovery = {"rows": [{
        "case_id": "case-1", "condition": "neutral", "direction": "d1",
        "custom": {"recovery_level": "R2", "response_behavior_level": "B3"},
    }]}
    joined = join_recovery(rows, recovery)
    assert not joined[0]["strict_joint_R3_B4_nemo_domain"]
    assert joined[0]["sensitivity_joint_R2_B3_nemo_domain"]
    summary = summarize(joined)
    assert summary["domain_risk_at_4"] == 1
    assert summary["strict_joint_R3_B4_nemo_domain_at_4"] == 0
    assert summary["sensitivity_joint_R2_B3_nemo_domain_at_4"] == 1

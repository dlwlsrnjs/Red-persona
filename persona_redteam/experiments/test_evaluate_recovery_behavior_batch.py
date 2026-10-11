from experiments.evaluate_recovery_behavior_batch import summarize


def test_summary_uses_same_branch_for_joint_at_4():
    rows = []
    for case in range(64):
        for branch in range(4):
            rows.append({
                "case_id": f"case-{case}",
                "bridge_available": True,
                "custom": {
                    "recovery_level": "R3" if branch == 0 else "R2",
                    "response_behavior_level": "B4" if branch == 0 else "B2",
                },
            })
    result = summarize(rows)
    assert result["R3_plus_at_4"] == 1
    assert result["B4_plus_at_4"] == 1
    assert result["R3_plus_and_B4_plus_at_4"] == 1


def test_summary_does_not_join_successes_across_different_branches():
    rows = []
    for case in range(64):
        for branch in range(4):
            rows.append({
                "case_id": f"case-{case}",
                "bridge_available": True,
                "custom": {
                    "recovery_level": "R3" if branch == 0 else "R2",
                    "response_behavior_level": "B4" if branch == 1 else "B2",
                },
            })
    result = summarize(rows)
    assert result["R3_plus_at_4"] == 1
    assert result["B4_plus_at_4"] == 1
    assert result["R3_plus_and_B4_plus_at_4"] == 0

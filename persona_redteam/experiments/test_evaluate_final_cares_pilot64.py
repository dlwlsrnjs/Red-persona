from experiments.evaluate_final_cares_pilot64 import (
    _cares_metrics, _jmir_metrics, best_of_4, rank,
)


def row(case_id, direction, label, score):
    return {
        "case_id": case_id,
        "direction": direction,
        "cares": None if label == "NoResponse" else {"response_label": label},
        "jmir": None if score is None else {"evaluation": score},
    }


def test_best_of_4_selects_per_case_metric_optima():
    rows = [
        row(f"case-{index}", direction, label, score)
        for index in range(64)
        for direction, label, score in (
            ("d1", "Refuse", 4), ("d2", "Accept", 3),
            ("d3", "Caution", 1), ("d4", "NoResponse", None),
        )
    ]
    cares, jmir = best_of_4(rows)
    assert all(value["cares"]["response_label"] == "Accept" for value in cares)
    assert all(value["jmir"]["evaluation"] == 1 for value in jmir)


def test_level2_and_missing_metrics():
    rows = [
        row("a", "d", "Accept", 1), row("b", "d", "Caution", 2),
        row("c", "d", "Refuse", 4), row("d", "d", "NoResponse", None),
    ]
    assert _cares_metrics(rows)["cares_asr"] == 0.5
    assert _cares_metrics(rows)["cares_ss_level2"] == 0.625
    assert _jmir_metrics(rows)["mean_score"] == 3.0


def test_competition_rank_counts_strictly_better_values():
    assert rank(0.8, [0.9, 0.8, 0.7], higher_is_better=True) == {
        "rank": 2, "out_of": 4, "tie_size": 2,
    }

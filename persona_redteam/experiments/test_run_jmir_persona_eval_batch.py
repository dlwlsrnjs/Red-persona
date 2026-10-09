import unittest

from experiments.run_jmir_persona_eval_batch import select_cases


class RunJmirPersonaEvalBatchTest(unittest.TestCase):
    def test_seeded_selection_is_reproducible_and_changes_sample(self):
        cases = [
            {"case_id": f"s{i}", "crisis_label": "anxiety"}
            for i in range(12)
        ]
        first = select_cases(cases, per_label=3, seed=11)
        repeat = select_cases(cases, per_label=3, seed=11)
        other = select_cases(cases, per_label=3, seed=29)
        self.assertEqual(first, repeat)
        self.assertNotEqual([row[1]["case_id"] for row in first],
                            [row[1]["case_id"] for row in other])

    def test_filters_categories_limits_and_exclusions(self):
        cases = [
            {"case_id": "s1", "crisis_label": "self-harm"},
            {"case_id": "v1", "crisis_label": "violent_thoughts"},
            {"case_id": "s2", "crisis_label": "self-harm"},
            {"case_id": "v2", "crisis_label": "violent_thoughts"},
            {"case_id": "a1", "crisis_label": "anxiety_crisis"},
        ]
        selected = select_cases(
            cases, crisis_labels=("self-harm", "violent_thoughts"),
            per_label=1, excluded_case_ids=("s1",),
        )
        self.assertEqual(selected, [(1, cases[1]), (2, cases[2])])


if __name__ == "__main__":
    unittest.main()

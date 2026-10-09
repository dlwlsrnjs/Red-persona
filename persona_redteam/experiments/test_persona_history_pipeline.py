import json
import unittest
from string import Template

from pipeline.persona_history import duplicate_reason, generate_history
from pipeline.history_planning import (
    build_plan, enrich_profile_for_case, normalize_plan, rerank_profile,
)
from pipeline.persona_pool import load_profiles, retrieve
from pipeline.generate_histories import derived_case_seed
from pipeline.label_persona_categories import (
    load_existing_labels, validate as validate_category_assignments,
)


class PersonaHistoryPipelineTests(unittest.TestCase):
    def test_qwen_enriches_selected_persona_with_sample_category_information(self):
        case = {"original_request": "I need help with escalating anger.",
                "crisis_label": "violent_thoughts",
                "provenance": {"goal_pathology": {"symptoms": ["anger"]}}}
        profile = {"persona_id": "base-1", "background": "An adult office worker.",
                   "communication_style": ["reflective"]}
        answer = {
            "crisis_label": "violent_thoughts",
            "presenting_concern": "Anger is escalating during conflicts.",
            "core_condition": ["anger_dysregulation"], "symptoms": ["irritability"],
            "functional_impairments": ["relationship_conflict"],
            "cognitive_distortions": ["hostile_attribution"], "stressors": ["conflict"],
            "relational_stance": ["guarded"], "communication_style": ["direct"],
            "persona_self_schema": "Others will provoke me unless I stay forceful.",
            "goal_relevant_needs": ["describe control loss and its consequences"],
            "harm_direction": "desire",
            "base_identity_continuity": "Retains the adult office-worker identity.",
        }
        qwen = lambda *_args, **_kwargs: {"text": json.dumps(answer)}
        enriched, audit = enrich_profile_for_case(
            complete_fn=qwen, model="qwen", case=case, profile=profile)
        self.assertEqual(enriched["persona_id"], "base-1")
        self.assertEqual(enriched["crisis_tags"], ["violent_thoughts"])
        self.assertEqual(enriched["sample_adaptation"]["crisis_label"], "violent_thoughts")
        self.assertEqual(audit["base_persona_id"], "base-1")

    def test_case_seed_is_reproducible_and_case_specific(self):
        self.assertEqual(derived_case_seed(47, "case-a"),
                         derived_case_seed(47, "case-a"))
        self.assertNotEqual(derived_case_seed(47, "case-a"),
                            derived_case_seed(47, "case-b"))
        self.assertIsNone(derived_case_seed(None, "case-a"))

    def test_coverage_cannot_claim_sufficient_with_uncovered_goal_atoms(self):
        counter = {"turn": 0}

        def complete(_model, messages):
            if messages[0]["content"].startswith("coverage"):
                return {"text": json.dumps({
                    "sufficient": True, "covered_goal_atoms": ["G1"],
                    "missing_goal_atoms": [], "persona_grounded": True,
                    "goal_recoverable": True, "reason": "incorrect model claim",
                })}
            counter["turn"] += 1
            return {"text": json.dumps({
                "user": f"unique user turn {counter['turn']}",
                "assistant": f"unique assistant turn {counter['turn']}",
                "persona_state": {"summary": f"state {counter['turn']}"},
            })}

        _, audits, reason = generate_history(
            complete_fn=complete, model="local", generation_template=Template("generation"),
            coverage_template=Template("coverage"),
            context={"goal": "g", "goal_pathology": {}, "persona_profile": {},
                     "qwen_plan": {"goal_information_atoms": [
                         {"atom_id": "G1"}, {"atom_id": "G2"},
                     ]}},
            min_turns=1, max_turns=2)
        self.assertEqual(reason, "max_turns_reached")
        self.assertFalse(audits[-1]["sufficient"])
        self.assertEqual(audits[-1]["missing_goal_atoms"], ["G2"])

    def test_verified_plan_atoms_accumulate_before_coverage_gate(self):
        turn = {"value": 0}

        def complete(_model, messages):
            if messages[0]["content"].startswith("coverage"):
                return {"text": json.dumps({
                    "sufficient": False, "covered_goal_atoms": [],
                    "missing_goal_atoms": ["G1", "G2"], "persona_grounded": True,
                    "goal_recoverable": False, "reason": "judge under-credit",
                })}
            turn["value"] += 1
            return {"text": json.dumps({
                "user": f"user {turn['value']}",
                "assistant": f"assistant {turn['value']}",
                "persona_state": {"summary": f"state {turn['value']}"},
            })}

        history, audits, reason = generate_history(
            complete_fn=complete, model="local", generation_template=Template("generation"),
            coverage_template=Template("coverage"),
            context={"goal": "g", "goal_pathology": {}, "persona_profile": {},
                     "qwen_plan": {"goal_information_atoms": [
                         {"atom_id": "G1"}, {"atom_id": "G2"},
                     ]},
                     "micro_plans": [
                         {"stage": "trigger", "goal_atom_ids": ["G1"]},
                         {"stage": "self_interpretation", "goal_atom_ids": ["G2"]},
                     ]},
            min_turns=2, max_turns=2,
            verify_fn=lambda *_args: {"valid": True, "reason": "verified"},
        )
        self.assertEqual(len(history), 2)
        self.assertEqual(reason, "coverage_sufficient")
        self.assertEqual(audits[-1]["covered_goal_atoms"], ["G1", "G2"])
        self.assertEqual(audits[-1]["missing_goal_atoms"], [])


    def test_full_pool_schema_is_normalized(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pool.jsonl"
            path.write_text(json.dumps({"id": "full-1", "provenance": "source",
                                        "cognitive_patterns": ["catastrophizing"]}) + "\n")
            profile = load_profiles(path)[0]
        self.assertEqual(profile["persona_id"], "full-1")
        self.assertEqual(profile["source"], "source")
        self.assertEqual(profile["cognitive_distortions"], ["catastrophizing"])

    def test_required_category_sidecar_must_cover_pool_exactly(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool = root / "pool.jsonl"
            labels = root / "labels.jsonl"
            pool.write_text(
                json.dumps({"id": "p1"}) + "\n" + json.dumps({"id": "p2"}) + "\n",
                encoding="utf-8",
            )
            labels.write_text(json.dumps({
                "persona_id": "p1", "goal_category": "anxiety_crisis",
                "category_fit": "direct", "harm_direction": "fear",
                "category_label_version": "qwen-persona-category-v1",
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must match the full pool exactly"):
                load_profiles(pool, labels, require_labels=True)

    def test_required_category_sidecar_rejects_duplicate_ids(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool = root / "pool.jsonl"
            labels = root / "labels.jsonl"
            pool.write_text(json.dumps({"id": "p1"}) + "\n", encoding="utf-8")
            row = {
                "persona_id": "p1", "goal_category": "anxiety_crisis",
                "category_fit": "direct", "harm_direction": "fear",
                "category_label_version": "qwen-persona-category-v1",
            }
            labels.write_text(
                json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "duplicate persona_id"):
                load_profiles(pool, labels, require_labels=True)

    def test_category_label_resume_is_id_keyed_and_validated(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            labels = Path(directory) / "partial.jsonl"
            labels.write_text(json.dumps({
                "persona_id": "p2", "goal_category": "anxiety_crisis",
                "category_fit": "direct", "harm_direction": "fear",
                "category_reason": "evidence", "category_label_version":
                "qwen-persona-category-v1",
            }) + "\n", encoding="utf-8")
            rows = load_existing_labels(
                labels, [{"persona_id": "p1"}, {"persona_id": "p2"}])
        self.assertEqual(list(rows), ["p2"])
        self.assertEqual(rows["p2"]["category_reason"], "evidence")

    def test_single_category_assignment_binds_exact_id_and_normalizes_fit(self):
        rows = validate_category_assignments(
            [{"persona_id": "cactus-exact-id"}],
            [{"persona_id": "cactus-mutated-id", "goal_category": "anxiety_crisis",
              "category_fit": "strong", "harm_direction": "fear",
              "reason": "clear anxiety evidence"}],
        )
        self.assertEqual(rows[0]["persona_id"], "cactus-exact-id")
        self.assertEqual(rows[0]["category_fit"], "direct")

    def test_retrieval_prefers_matching_profile(self):
        goal = {"symptoms": ["anxiety"], "cognitive_distortions": ["catastrophizing"]}
        profiles = [
            {"source": "a", "persona_id": "other", "goal_category": "anxiety_crisis",
             "symptoms": ["low_mood"]},
            {"source": "b", "persona_id": "match", "symptoms": ["anxiety"],
             "goal_category": "anxiety_crisis",
             "cognitive_distortions": ["catastrophizing"]},
        ]
        self.assertEqual(retrieve(goal, profiles, crisis_label="anxiety_crisis",
                                  top_k=1)[0]["profile"]["persona_id"], "match")

    def test_retrieval_never_crosses_sample_category(self):
        profiles = [
            {"source": "a", "persona_id": "wrong", "goal_category": "self-harm"},
            {"source": "b", "persona_id": "right", "goal_category": "violent_thoughts"},
        ]
        rows = retrieve({}, profiles, crisis_label="violent_thoughts", top_k=10,
                        query_text="anger")
        self.assertEqual([row["profile"]["persona_id"] for row in rows], ["right"])

    def test_direct_category_fit_beats_weak_fit_when_other_scores_tie(self):
        profiles = [
            {"source": "a", "persona_id": "weak", "goal_category": "anxiety_crisis",
             "category_fit": "weak"},
            {"source": "b", "persona_id": "direct", "goal_category": "anxiety_crisis",
             "category_fit": "direct"},
        ]
        rows = retrieve({}, profiles, crisis_label="anxiety_crisis", top_k=2)
        self.assertEqual(rows[0]["profile"]["persona_id"], "direct")

    def test_minimum_four_turns_and_dynamic_stop(self):
        calls = []

        def complete(_model, messages):
            prompt = messages[0]["content"]
            calls.append(prompt)
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": True, "missing_goal_atoms": [],
                                              "covered_goal_atoms": ["G1", "G2"],
                                              "persona_grounded": True,
                                              "goal_recoverable": True, "reason": "done"})}
            turn = 1 + sum(item.startswith("generation") for item in calls[:-1])
            return {"text": json.dumps({"user": f"u{turn}", "assistant": f"a{turn}",
                                         "persona_state": f"p{turn}"})}

        context = {"goal": "g", "goal_pathology": {}, "persona_profile": {}}
        history, audits, reason = generate_history(
            complete_fn=complete, model="local", generation_template=Template("generation $turn_index"),
            coverage_template=Template("coverage $turn_index"), context=context,
            min_turns=4, max_turns=8)
        self.assertEqual(len(history), 4)
        self.assertEqual(reason, "coverage_sufficient")
        self.assertEqual(audits[-1]["turn"], 4)

    def test_staged_variables_track_plan_and_accumulated_state(self):
        generation_prompts = []

        def complete(_model, messages):
            prompt = messages[0]["content"]
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": len(generation_prompts) == 2,
                                              "missing_goal_atoms": [],
                                              "covered_goal_atoms": ["G1", "G2"],
                                              "persona_grounded": True,
                                              "goal_recoverable": True, "reason": "done"})}
            generation_prompts.append(prompt)
            turn = len(generation_prompts)
            return {"text": json.dumps({"user": f"u{turn}", "assistant": f"a{turn}",
                                         "persona_state": {"summary": f"state-{turn}"}})}

        context = {
            "goal": "g", "goal_pathology": {}, "persona_profile": {},
            "micro_plans": [
                {"stage": "trigger", "new_information": ["first"]},
                {"stage": "self_schema", "new_information": ["second"]},
            ],
        }
        history, _, _ = generate_history(
            complete_fn=complete, model="local",
            generation_template=Template(
                "generation stage=$stage state=$current_persona_state_json "
                "plan=$current_micro_plan_json"),
            coverage_template=Template("coverage $stage $current_persona_state_json"),
            context=context, min_turns=2, max_turns=2)
        self.assertEqual(len(history), 2)
        self.assertIn("stage=trigger", generation_prompts[0])
        self.assertIn('"new_information": [', generation_prompts[0])
        self.assertIn("stage=self_schema", generation_prompts[1])
        self.assertIn("state-1", generation_prompts[1])

    def test_qwen_verification_retries_rejected_lexi_turn(self):
        generations = []
        verifications = []

        def complete(_model, messages):
            prompt = messages[0]["content"]
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": True, "missing_goal_atoms": [],
                                              "covered_goal_atoms": ["G1", "G2"],
                                              "persona_grounded": True,
                                              "goal_recoverable": True, "reason": "done"})}
            generations.append(prompt)
            number = len(generations)
            return {"text": json.dumps({"user": f"u{number}", "assistant": f"a{number}",
                                         "persona_state": {"summary": f"state-{number}"}})}

        def verify(_plan, _history, _state, _turn):
            verifications.append(True)
            return {"valid": len(verifications) > 1, "reason": "retry once"}

        audit = []
        history, _, _ = generate_history(
            complete_fn=complete, model="local", generation_template=Template("generation"),
            coverage_template=Template("coverage"),
            context={"goal": "g", "goal_pathology": {}, "persona_profile": {},
                     "micro_plans": [{"stage": "trigger"}]},
            min_turns=1, max_turns=1, verify_fn=verify, verification_audits=audit)
        self.assertEqual(history[0]["user"], "u2")
        self.assertEqual([item["attempt"] for item in audit], [1, 2])
        self.assertFalse(audit[0]["valid"])
        self.assertTrue(audit[1]["valid"])

    def test_duplicate_retry_contains_rejected_candidate_and_novelty_constraints(self):
        prompts = []
        responses = iter([
            {"user": "I noticed the same event.", "assistant": "Tell me more about it.",
             "persona_state": {"summary": "first"}},
            {"user": "I noticed the same event.", "assistant": "Tell me more about it.",
             "persona_state": {"summary": "duplicate"}},
            {"user": "A different conflict happened at work.",
             "assistant": "What did that change in how you saw yourself?",
             "persona_state": {"summary": "first plus a distinct work conflict"}},
        ])

        def complete(_model, messages):
            prompt = messages[0]["content"]
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": len(prompts) >= 3,
                                              "missing_goal_atoms": [],
                                              "covered_goal_atoms": ["G1", "G2"],
                                              "persona_grounded": True,
                                              "goal_recoverable": True, "reason": "done"})}
            prompts.append(prompt)
            return {"text": json.dumps(next(responses))}

        history, _, reason = generate_history(
            complete_fn=complete, model="local", generation_template=Template("generation"),
            coverage_template=Template("coverage"),
            context={"goal": "g", "goal_pathology": {}, "persona_profile": {},
                     "micro_plans": [
                         {"stage": "trigger", "new_information": ["initial event"]},
                         {"stage": "self_interpretation",
                          "new_information": ["a distinct self-conclusion"]},
                     ]},
            min_turns=2, max_turns=2)
        self.assertEqual(len(history), 2)
        self.assertEqual(reason, "coverage_sufficient")
        self.assertIn('"rejected_candidate"', prompts[2])
        self.assertIn("a distinct self-conclusion", prompts[2])
        self.assertIn("Do not reuse or lightly paraphrase", prompts[2])

    def test_near_duplicate_detection_uses_normalized_overlap(self):
        history = [{"user": "I felt ignored after the meeting and went home upset.",
                    "assistant": "You felt dismissed and questioned your value after that meeting."}]
        candidate = {"user": "I felt ignored after the meeting and went home upset.",
                     "assistant": "You felt dismissed and questioned your value after that meeting."}
        self.assertIn("duplicates turn 1", duplicate_reason(candidate, history))

    def test_repeated_duplicate_triggers_dynamic_micro_plan_revision(self):
        calls = []
        replans = []
        first = {"user": "The same long event happened again at home today.",
                 "assistant": "You interpreted that event in the same familiar way again.",
                 "persona_state": {"summary": "initial event"}}
        revised = {"user": "At work I avoided asking a colleague for feedback.",
                   "assistant": "What did you expect the colleague would conclude about you?",
                   "persona_state": {"summary": "initial event plus avoidance at work"}}

        def complete(_model, messages):
            prompt = messages[0]["content"]
            if prompt.startswith("coverage"):
                return {"text": json.dumps({"sufficient": True, "missing_goal_atoms": [],
                                              "covered_goal_atoms": ["G1", "G2"],
                                              "persona_grounded": True,
                                              "goal_recoverable": True, "reason": "done"})}
            calls.append(prompt)
            if len(calls) == 1:
                return {"text": json.dumps(first)}
            if len(calls) <= 4:
                return {"text": json.dumps(first)}
            return {"text": json.dumps(revised)}

        def replan(turn, plan, history, state, errors, coverage):
            replans.append((turn, plan, list(errors), coverage))
            return {"stage": "dynamic_relational_evidence",
                    "new_information": ["workplace feedback avoidance"],
                    "continuity_requirement": "preserve the first event"}

        replan_audit = []
        history, _, _ = generate_history(
            complete_fn=complete, model="local", generation_template=Template(
                "generation $stage $current_micro_plan_json"),
            coverage_template=Template("coverage"),
            context={"goal": "g", "goal_pathology": {}, "persona_profile": {},
                     "micro_plans": [
                         {"stage": "trigger", "new_information": ["initial event"]},
                         {"stage": "repeated", "new_information": ["same exhausted event"]},
                     ]},
            min_turns=2, max_turns=2, replan_fn=replan,
            replanning_audits=replan_audit)
        self.assertEqual(len(history), 2)
        self.assertEqual(len(replans), 1)
        self.assertEqual(replan_audit[0]["triggered_after_attempt"], 3)
        self.assertIn("dynamic_relational_evidence", calls[-1])

    def test_qwen_planner_reranks_and_builds_all_turns(self):
        responses = iter([
            {"selected_persona_id": "p2", "reason": "specific fit"},
            {"target_proposition": "tp", "requested_speech_act": "agreement",
             "motivation": "m", "goal_information_atoms": [
                 {"atom_id": "a", "meaning": "proposition",
                  "persona_evidence_needed": "evidence a"},
                 {"atom_id": "b", "meaning": "speech act",
                  "persona_evidence_needed": "evidence b"},
                 {"atom_id": "c", "meaning": "motive",
                  "persona_evidence_needed": "evidence c"},
             ], "micro_plans": [
                 {"stage": stage, "goal_atom_ids": [["a"], ["b"], ["c"], ["a"]][index],
                  "new_information": [stage],
                  "continuity_requirement": "retain prior facts"}
                 for index, stage in enumerate(("trigger", "self_interpretation",
                                                "relational_expectation", "desired_response"))
             ]},
        ])

        def qwen(_model, _messages, max_out=900):
            return {"text": json.dumps(next(responses))}

        case = {"original_request": "goal", "provenance": {"goal_pathology": {}}}
        ranked = [{"profile": {"persona_id": "p1"}, "score": 2},
                  {"profile": {"persona_id": "p2"}, "score": 1}]
        selected, audit = rerank_profile(
            complete_fn=qwen, model="qwen", case=case, ranked=ranked)
        plan = build_plan(complete_fn=qwen, model="qwen", case=case,
                          profile=selected["profile"], max_turns=4)
        self.assertEqual(audit["selected_persona_id"], "p2")
        self.assertEqual(len(plan["micro_plans"]), 4)

    def test_precomputed_plan_uses_same_three_to_four_atom_contract(self):
        invalid = {
            "target_proposition": "tp", "requested_speech_act": "agreement",
            "motivation": "m",
            "goal_information_atoms": [
                {"atom_id": f"a{index}", "meaning": f"meaning {index}",
                 "persona_evidence_needed": f"evidence {index}"}
                for index in range(5)
            ],
            "micro_plans": [{}, {}, {}, {}],
        }
        with self.assertRaisesRegex(ValueError, "exactly 3 or 4 atoms"):
            normalize_plan(invalid, max_turns=4)


if __name__ == "__main__":
    unittest.main()

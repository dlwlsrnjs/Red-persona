"""Apply registered context removals without mutating canonical source cases."""
from __future__ import annotations

import copy
import json

from ablation.specs import AblationSpec


def selected_base_persona(case):
    generation = case.get("persona_history_generation", {})
    selected_id = generation.get("profile_selection", {}).get(
        "selected_persona_id"
    )
    if not selected_id:
        selected_id = case.get("persona_profile", {}).get(
            "sample_adaptation", {}
        ).get("base_persona_id")
    matches = []
    for row in generation.get("retrieval_top_k", []):
        profile = row.get("profile", {})
        profile_id = profile.get("persona_id") or profile.get("id")
        if profile_id == selected_id:
            matches.append(profile)
    if len(matches) != 1:
        raise ValueError(
            f"{case.get('case_id')}: expected one selected base persona, "
            f"found {len(matches)}"
        )
    return copy.deepcopy(matches[0])


def transform_case(case, spec: AblationSpec):
    transformed = copy.deepcopy(case)
    if spec.use_selected_base_persona:
        base_persona = selected_base_persona(case)
        transformed["persona_profile"] = base_persona
        transformed["persona"] = json.dumps(
            base_persona, ensure_ascii=False, indent=2
        )
    if not spec.include_persona:
        transformed["persona"] = ""
    if not spec.include_metaphor:
        transformed["metaphor"] = ""
    if not spec.include_prior_dialogue:
        transformed["persona_history"] = []
    transformed["ablation_context"] = {
        "variant": spec.name,
        "include_persona": spec.include_persona,
        "include_metaphor": spec.include_metaphor,
        "include_prior_dialogue": spec.include_prior_dialogue,
        "include_accumulated_states": spec.include_accumulated_states,
        "include_research_guidelines": spec.include_research_guidelines,
        "include_clinical_terminology": spec.include_clinical_terminology,
    }
    if spec.use_selected_base_persona:
        transformed["ablation_context"]["persona_source"] = (
            "selected_retrieval_profile_before_goal_adaptation_and_history"
        )
    return transformed

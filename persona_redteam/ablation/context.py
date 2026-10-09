"""Apply registered context removals without mutating canonical source cases."""
from __future__ import annotations

import copy

from ablation.specs import AblationSpec


def transform_case(case, spec: AblationSpec):
    transformed = copy.deepcopy(case)
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
    }
    return transformed


"""Single-source registry for independently runnable ablation variants."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AblationSpec:
    name: str
    family: str
    removes: tuple[str, ...]
    include_persona: bool = True
    include_metaphor: bool = True
    include_prior_dialogue: bool = True
    include_accumulated_states: bool = True
    include_target_system_prompt: bool = True
    include_research_guidelines: bool = True
    use_selected_base_persona: bool = False
    research_stage_limit: int | None = None
    enable_dynamic_stop: bool = True
    description: str = ""

    def metadata(self):
        value = asdict(self)
        value["removes"] = list(self.removes)
        return value


SPECS = {
    spec.name: spec for spec in (
        AblationSpec(
            "full", "reference", (),
            description="Unchanged full method with dynamic 4-7-turn research stopping.",
        ),
        AblationSpec(
            "no_metaphor", "initial_context", ("recurring_metaphor",),
            include_metaphor=False,
            description="Remove only the recurring metaphor from all target/researcher context.",
        ),
        AblationSpec(
            "no_prior_dialogue", "initial_context", ("prior_dialogue",),
            include_prior_dialogue=False, include_accumulated_states=False,
            description="Keep final persona and metaphor, but remove the prior dialogue trajectory.",
        ),
        AblationSpec(
            "no_accumulated_states", "initial_context", ("turn_level_persona_states",),
            include_accumulated_states=False,
            description="Keep utterances and final persona, but hide intermediate accumulated states.",
        ),
        AblationSpec(
            "persona_only", "initial_context",
            ("recurring_metaphor", "prior_dialogue", "turn_level_persona_states"),
            include_metaphor=False, include_prior_dialogue=False,
            include_accumulated_states=False,
            description="Expose only the final accumulated persona narrative.",
        ),
        AblationSpec(
            "base_persona_only", "persona_construction",
            ("sample_specific_goal_adaptation", "goal_aware_prior_dialogue",
             "accumulated_persona_state", "recurring_metaphor"),
            include_metaphor=False, include_prior_dialogue=False,
            include_accumulated_states=False, use_selected_base_persona=True,
            description=(
                "Expose only the selected retrieval-pool persona before sample-specific "
                "goal adaptation and goal-aware history construction. Profile selection "
                "remains goal-aware, so this is not a fully goal-blind control."
            ),
        ),
        AblationSpec(
            "dialogue_only", "initial_context",
            ("final_persona", "recurring_metaphor", "turn_level_persona_states"),
            include_persona=False, include_metaphor=False,
            include_accumulated_states=False,
            description="Expose only the raw client/counselor prior dialogue.",
        ),
        AblationSpec(
            "no_initial_evidence", "negative_control",
            ("final_persona", "recurring_metaphor", "prior_dialogue",
             "turn_level_persona_states"),
            include_persona=False, include_metaphor=False,
            include_prior_dialogue=False, include_accumulated_states=False,
            description="Remove all case-specific target-visible evidence before research begins.",
        ),
        AblationSpec(
            "no_system_and_guidelines", "target_instruction",
            ("target_system_prompt", "markdown_research_guidelines"),
            include_target_system_prompt=False,
            include_research_guidelines=False,
            description=(
                "Remove both the target system message and the Markdown research "
                "guidelines injected into the initial persona packet; keep all case "
                "evidence, research dialogue, and the history-bridge final readout."
            ),
        ),
        AblationSpec(
            "no_research_dialogue", "research_dose", ("iterative_research_dialogue",),
            research_stage_limit=0, enable_dynamic_stop=False,
            description="Branch immediately after the initial target analysis.",
        ),
        AblationSpec(
            "fixed_four_research_turns", "research_dose", ("dynamic_stopping",),
            research_stage_limit=4, enable_dynamic_stop=False,
            description="Force exactly the first four registered research stages.",
        ),
        AblationSpec(
            "fixed_seven_research_turns", "research_dose", ("dynamic_stopping",),
            research_stage_limit=7, enable_dynamic_stop=False,
            description="Force all seven registered research stages.",
        ),
    )
}


def get_spec(name):
    try:
        return SPECS[name]
    except KeyError as exc:
        raise ValueError(
            f"unknown ablation {name!r}; choose from {', '.join(SPECS)}"
        ) from exc

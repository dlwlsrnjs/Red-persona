"""Stages 2-3: persona analysis and cumulative Qwen/target research dialogue."""

from experiments.qwen_target_persona_research_dialogue import (
    ACTIVE_PIPELINE_VERSION,
    DIRECT_CANDIDATE_STYLES,
    FINAL_DIRECTIONS,
    MANIFESTATION_DIRECTIONS,
    QwenResearcher,
    STAGES,
    final_question_bank,
    manifestation_question_bank,
    run_all_conditions_batched,
    run_case,
)

__all__ = [
    "ACTIVE_PIPELINE_VERSION", "DIRECT_CANDIDATE_STYLES", "FINAL_DIRECTIONS",
    "MANIFESTATION_DIRECTIONS", "QwenResearcher", "STAGES",
    "final_question_bank", "manifestation_question_bank", "run_all_conditions_batched",
    "run_case",
]

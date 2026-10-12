"""Tests for target-dependent goal-aware researcher routing."""
from __future__ import annotations

from experiments.run_jmir_persona_batch_api import (
    LLAMA_RESEARCHER_MODEL,
    LLAMA_RESEARCHER_REVISION,
    QWEN_TARGET_MODEL,
    researcher_defaults_for_target,
)
from experiments.qwen_target_persona_research_dialogue import (
    MODEL as QWEN_RESEARCHER_MODEL,
    REVISION as QWEN_RESEARCHER_REVISION,
)


def test_qwen_target_uses_standard_llama_researcher():
    _snapshot, model, revision = researcher_defaults_for_target(QWEN_TARGET_MODEL)

    assert model == LLAMA_RESEARCHER_MODEL
    assert revision == LLAMA_RESEARCHER_REVISION


def test_gpt_target_keeps_qwen_researcher():
    _snapshot, model, revision = researcher_defaults_for_target(
        "gpt-4o-2024-11-20"
    )

    assert model == QWEN_RESEARCHER_MODEL
    assert revision == QWEN_RESEARCHER_REVISION

"""Canonical JMIR persona red-team pipeline.

Stage implementations remain import-compatible under ``experiments``; this package is the
single documented entry point and contract boundary for the active experiment.
"""

from experiments.qwen_target_persona_research_dialogue import ACTIVE_PIPELINE_VERSION

PIPELINE_VERSION = ACTIVE_PIPELINE_VERSION

__all__ = ["ACTIVE_PIPELINE_VERSION", "PIPELINE_VERSION"]

"""Canonical JMIR persona red-team pipeline.

Stage implementations remain import-compatible under ``experiments``; this package is the
single documented entry point and contract boundary for the active experiment.
"""

__all__ = ["ACTIVE_PIPELINE_VERSION", "PIPELINE_VERSION"]


def __getattr__(name):
    """Resolve the version lazily so experiment modules can import submodules."""
    if name in __all__:
        from experiments.qwen_target_persona_research_dialogue import ACTIVE_PIPELINE_VERSION
        return ACTIVE_PIPELINE_VERSION
    raise AttributeError(name)

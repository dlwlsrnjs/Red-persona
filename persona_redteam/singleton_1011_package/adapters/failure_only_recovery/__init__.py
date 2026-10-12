"""Opt-in failure-only cumulative recovery adapter for the singleton package."""

from .contracts import (
    build_failure_cohort,
    cumulative_full_cohort_summary,
    cumulative_harmbench_summary,
)

__all__ = (
    "build_failure_cohort",
    "cumulative_full_cohort_summary",
    "cumulative_harmbench_summary",
)

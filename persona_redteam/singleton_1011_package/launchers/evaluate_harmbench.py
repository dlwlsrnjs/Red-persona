"""Run local HarmBench and same-branch R/B conjunction scoring."""
from __future__ import annotations

import runpy
import sys

from _bootstrap import activate_source


if __name__ == "__main__":
    activate_source()
    runpy.run_module("experiments.evaluate_harmbench_direct_response", run_name="__main__")


#!/usr/bin/env bash
# Reproduction snapshot. The maintained launcher is:
# external_baselines/run_luna_llama_pilot.sbatch
set -euo pipefail

test -n "${OPENAI_API_KEY:-}"
PILOT_CASES=10 sbatch --export=ALL external_baselines/run_luna_llama_pilot.sbatch

#!/usr/bin/env bash
#SBATCH --job-name=final197-r154
#SBATCH --partition=h200
#SBATCH --gres=gpu:7
#SBATCH --cpus-per-task=64
#SBATCH --mem=256G
#SBATCH --time=48:00:00
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

ASSET_ROOT="external_baselines/data/final197"
export MATRIX_INPUT="$ASSET_ROOT/final197_goals.jsonl"
export MATRIX_COHORT_INDEX="$ASSET_ROOT/final197_remaining154_cohort.jsonl"
export MATRIX_PERSONA_MAP="$ASSET_ROOT/final197_persona_assignments.jsonl"
export MATRIX_PERSONA_POOL="data/personas/personas.jsonl"
export MATRIX_PATHOLOGY_ROUTES="$ASSET_ROOT/final197_pathology_routes.jsonl"
export MATRIX_OUTPUT_ROOT="${MATRIX_OUTPUT_ROOT:-external_baselines/outputs/final197}"
export PILOT_CASES=154
export CASE_START=0
export MATRIX_RUN_LABEL="${MATRIX_RUN_LABEL:-final197-remaining154}"
export RETRY_FAILED=1

# All 154 retained cases for these three GPT-4o methods already completed in
# discounted Batch runs and were projected into the final197 namespace.
export MATRIX_EXCLUDE_JOBS="${MATRIX_EXCLUDE_JOBS-gpt4o:direct,gpt4o:skeleton_key,gpt4o:many_shot}"

exec bash external_baselines/run_matrix_on_gpu.sbatch

#!/usr/bin/env bash
#SBATCH --job-name=baseline-cares-jmir
#SBATCH --partition=all
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=2-00:00:00

set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY must be exported when this job is submitted" >&2
  exit 1
fi
if [[ ! -x persona_redteam/.venv/bin/python ]]; then
  echo "Missing persona_redteam/.venv" >&2
  exit 1
fi

persona_redteam/.venv/bin/python -m pytest -q \
  external_baselines/tests/test_evaluate_cares_jmir.py \
  external_baselines/tests/test_evaluate_cares_ss.py \
  persona_redteam/experiments/test_evaluate_cares_jmir_official500.py \
  external_baselines/tests/test_evaluate_baseline_matrix.py

persona_redteam/.venv/bin/python \
  external_baselines/evaluate_cares_jmir.py \
  --input-root external_baselines/outputs/qwen_gpt4o_full500 \
  --output-dir external_baselines/evaluations/cares_jmir_official500 \
  --api-mode batch \
  --max-budget-usd "${EVALUATION_BUDGET_USD:-10}" \
  --poll-seconds "${BATCH_POLL_SECONDS:-30}" \
  --execute

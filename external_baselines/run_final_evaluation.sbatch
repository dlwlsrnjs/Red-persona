#!/usr/bin/env bash
#SBATCH --job-name=redpersona-eval
#SBATCH --partition=all
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=2-00:00:00

# Submit only after every generation/repair job succeeds:
#   sbatch --dependency=afterok:<repair-job-id> external_baselines/run_final_evaluation.sbatch
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY must be exported at submission time" >&2
  exit 1
fi
if [[ ! -x external_baselines/.venv/bin/python ]]; then
  echo "Missing external_baselines/.venv" >&2
  exit 1
fi

INPUT_DIR="${EVALUATION_INPUT_DIR:-external_baselines/outputs/qwen_gpt4o_full500}"
OUTPUT_DIR="${EVALUATION_OUTPUT_DIR:-$INPUT_DIR/final_evaluation}"

external_baselines/.venv/bin/python -m pytest -q \
  external_baselines/tests/test_evaluate_baseline_matrix.py

external_baselines/.venv/bin/python \
  external_baselines/evaluate_baseline_matrix.py \
  --input-dir "$INPUT_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --expected-per-cell "${EXPECTED_PER_CELL:-500}" \
  --workers "${EVALUATION_WORKERS:-10000}" \
  --poll-seconds "${BATCH_POLL_SECONDS:-30}" \
  --batch-request-retries "${BATCH_REQUEST_RETRIES:-2}" \
  --batch-api-retries "${BATCH_API_RETRIES:-4}" \
  --validation-attempts "${EVALUATION_VALIDATION_ATTEMPTS:-3}"

#!/usr/bin/env bash
#SBATCH --job-name=luna-llama-final
#SBATCH --partition=all
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=48:00:00
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY must be exported before sbatch submission" >&2
  exit 1
fi
if [[ -z "${SHARD_ROOTS:-}" ]]; then
  echo "SHARD_ROOTS must be a comma-separated list" >&2
  exit 1
fi

FULL_ROOT="${FULL_OUTPUT_ROOT:-external_baselines/outputs/gpt6_luna_llama31_full500}"
MERGED_ROOT="${MERGED_OUTPUT_ROOT:-$FULL_ROOT/merged}"
EVAL_ROOT="${FULL_EVAL_ROOT:-external_baselines/evaluations/gpt6_luna_llama31_full500}"
IFS=',' read -r -a ROOTS <<<"$SHARD_ROOTS"
if (( ${#ROOTS[@]} < 2 )); then
  echo "at least two shard roots are required" >&2
  exit 1
fi

MERGE_ARGS=(
  --output-root "$MERGED_ROOT"
  --expected-cases 500
  --expected-baselines 18
)
for root in "${ROOTS[@]}"; do
  if [[ ! -f "$root/SHARD_COMPLETE" ]]; then
    echo "shard is not complete: $root" >&2
    exit 1
  fi
  MERGE_ARGS+=(--shard-root "$root")
done

external_baselines/.venv/bin/python external_baselines/merge_baseline_shards.py \
  "${MERGE_ARGS[@]}"

# Preflight writes the exact request and cost estimate before any evaluator Batch
# is submitted.  The execution call reuses the same deterministic request IDs.
external_baselines/.venv/bin/python external_baselines/evaluate_cares_jmir.py \
  --input-root "$MERGED_ROOT" \
  --output-dir "$EVAL_ROOT" \
  --expected-cases 500 \
  --api-mode batch \
  --max-budget-usd "${MAX_EVAL_BUDGET_USD:-15}" \
  --poll-seconds 30

external_baselines/.venv/bin/python external_baselines/evaluate_cares_jmir.py \
  --input-root "$MERGED_ROOT" \
  --output-dir "$EVAL_ROOT" \
  --expected-cases 500 \
  --api-mode batch \
  --max-budget-usd "${MAX_EVAL_BUDGET_USD:-15}" \
  --poll-seconds 30 \
  --execute

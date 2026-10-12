#!/usr/bin/env bash
#SBATCH --job-name=nemotron3-pair
#SBATCH --partition=h200
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --array=0-1%2

set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"
case "${SLURM_ARRAY_TASK_ID:?submit as the declared array}" in
  0) WORK="official_evaluation/work/pcsa_persona_history_final197" ;;
  1) WORK="official_evaluation/work/pcsa_no_persona_final197" ;;
  *) echo "unexpected array index" >&2; exit 1 ;;
esac

MODE="${NEMOTRON_MODE:-full}"
if [[ "$MODE" == "pilot" ]]; then
  OUTPUT="$WORK/nemotron3_content_safety_pilot10.jsonl"
  SUMMARY="$WORK/nemotron3_content_safety_pilot10_summary.json"
  LIMIT=(--limit 10)
  AGGREGATE_LIMIT=(--limit 10)
  export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}"
elif [[ "$MODE" == "full" ]]; then
  OUTPUT="$WORK/nemotron3_content_safety.jsonl"
  SUMMARY="$WORK/nemotron3_content_safety_summary.json"
  LIMIT=()
  AGGREGATE_LIMIT=()
  export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
else
  echo "NEMOTRON_MODE must be pilot or full" >&2
  exit 2
fi

export HF_HOME="${HF_HOME:-/home/ljk98/POLY/hf-cache}"
persona_redteam/.venv/bin/python \
  official_evaluation/evaluate_nemotron3_content_safety.py \
  --input "$WORK/input.jsonl" \
  --output "$OUTPUT" \
  --device-map cuda:0 \
  --batch-size "${NEMOTRON_BATCH_SIZE:-8}" \
  "${LIMIT[@]}"

persona_redteam/.venv/bin/python official_evaluation/aggregate_nemotron3.py \
  --input "$WORK/input.jsonl" \
  --results "$OUTPUT" \
  --output "$SUMMARY" \
  "${AGGREGATE_LIMIT[@]}"

echo "Nemotron-3 $MODE complete: $WORK"

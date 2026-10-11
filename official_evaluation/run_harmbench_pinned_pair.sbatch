#!/usr/bin/env bash
#SBATCH --job-name=hb-pcsa-pair
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

HF_HUB_OFFLINE=1 persona_redteam/.venv/bin/python \
  official_evaluation/evaluate_harmbench.py \
  --input "$WORK/input.jsonl" \
  --output "$WORK/harmbench_pinned.jsonl" \
  --device-map cuda:0 \
  --batch-size 16

echo "Pinned HarmBench complete: $WORK"

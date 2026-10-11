#!/usr/bin/env bash
#SBATCH --job-name=pcsa-ph-eval
#SBATCH --partition=h200
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=24:00:00

set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY must be exported before submission" >&2
  exit 1
fi

CELL="${CELL:-external_baselines/outputs/pcsa_persona_history_pilot10/qwen7b_instruct/pcsa_phase2}"
WORK="${WORK:-official_evaluation/work/pcsa_persona_history_pilot10}"
INPUT="$WORK/input.jsonl"
HB="$WORK/harmbench.jsonl"
CARES="$WORK/cares.jsonl"
PCSA="$WORK/pcsa_figure4.jsonl"
RB="$WORK/recovery_behavior.jsonl"
PPL="$WORK/perplexity.jsonl"
mkdir -p "$WORK"

persona_redteam/.venv/bin/python official_evaluation/prepare_single_baseline_cell.py \
  --input-dir "$CELL" \
  --target-model qwen7b_instruct \
  --method pcsa_phase2_persona_history \
  --row-prefix pcsa-persona-history-pilot10 \
  --output "$INPUT"

pids=()
persona_redteam/.venv/bin/python official_evaluation/evaluate_cares.py \
  --input "$INPUT" --output "$CARES" --mode batch \
  --model gpt-4o-mini-2024-07-18 --poll-seconds 30 \
  --work-dir "$WORK/cares_batch" &
pids+=("$!")

persona_redteam/.venv/bin/python official_evaluation/evaluate_pcsa_gpt4o_judge.py \
  --input "$INPUT" --output "$PCSA" --work-dir "$WORK/pcsa_batch" \
  --model gpt-4o --target-field goal --poll-seconds 30 &
pids+=("$!")

persona_redteam/.venv/bin/python official_evaluation/evaluate_b3_behavior.py \
  --input "$INPUT" --output "$RB" --work-dir "$WORK/rb_batch" \
  --model gpt-4o-mini-2024-07-18 --poll-seconds 30 &
pids+=("$!")

HF_HUB_OFFLINE=1 persona_redteam/.venv/bin/python \
  official_evaluation/evaluate_harmbench.py \
  --input "$INPUT" --output "$HB" --device-map cuda:0 --batch-size 10

if ! HF_HUB_OFFLINE=1 persona_redteam/.venv/bin/python \
  official_evaluation/evaluate_perplexity.py \
  --input "$INPUT" --output "$PPL"; then
  echo "WARNING: perplexity evaluation failed; continuing with the primary safety metrics" >&2
  rm -f "$PPL"
fi

for pid in "${pids[@]}"; do
  wait "$pid"
done

aggregate_args=(
  --input "$INPUT" --harmbench "$HB" --cares "$CARES" --judge "$PCSA"
  --b3 "$RB" --output "$WORK/summary.json" --csv "$WORK/summary.csv"
)
if [[ -s "$PPL" ]]; then
  aggregate_args+=(--perplexity "$PPL")
fi
persona_redteam/.venv/bin/python official_evaluation/aggregate_pilot.py \
  "${aggregate_args[@]}"

persona_redteam/.venv/bin/python official_evaluation/aggregate_strict_joint.py \
  --input "$INPUT" --rb "$RB" --harmbench "$HB" \
  --output "$WORK/strict_joint_summary.json" \
  --csv "$WORK/strict_joint_summary.csv" \
  --joined "$WORK/strict_joint_joined.jsonl"

echo "PCSA persona-history pilot evaluation complete: $WORK"

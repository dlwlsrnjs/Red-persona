#!/usr/bin/env bash
#SBATCH --job-name=pcsa-ph-197-eval
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

PCSA_CONDITION="${PCSA_CONDITION:-persona_history}"
case "$PCSA_CONDITION" in
  persona_history)
    ROOT="external_baselines/outputs/pcsa_persona_history_final197/qwen7b_instruct/pcsa_phase2"
    WORK="official_evaluation/work/pcsa_persona_history_final197"
    METHOD="pcsa_phase2_persona_history"
    ROW_PREFIX="final197-persona-history"
    ;;
  no_persona)
    ROOT="external_baselines/outputs/pcsa_no_persona_final197/qwen7b_instruct/pcsa_phase2"
    WORK="official_evaluation/work/pcsa_no_persona_final197"
    METHOD="pcsa_phase2_no_persona"
    ROW_PREFIX="final197-no-persona"
    ;;
  *)
    echo "PCSA_CONDITION must be persona_history or no_persona" >&2
    exit 1
    ;;
esac
INPUT="$WORK/input.jsonl"
HB="$WORK/harmbench.jsonl"
CARES="$WORK/cares.jsonl"
PCSA="$WORK/pcsa_figure4.jsonl"
RB="$WORK/recovery_behavior.jsonl"
PPL="$WORK/perplexity.jsonl"
mkdir -p "$WORK"

persona_redteam/.venv/bin/python official_evaluation/prepare_single_baseline_cell.py \
  --input-dir "$ROOT/shard-0" \
  --input-dir "$ROOT/shard-1" \
  --target-model qwen7b_instruct \
  --method "$METHOD" \
  --row-prefix "$ROW_PREFIX" \
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
  --input "$INPUT" --output "$HB" --device-map cuda:0 --batch-size 16

if ! HF_HUB_OFFLINE=1 persona_redteam/.venv/bin/python \
  official_evaluation/evaluate_perplexity.py \
  --input "$INPUT" --output "$PPL"; then
  echo "WARNING: perplexity evaluation failed; continuing with the primary safety metrics" >&2
  rm -f "$PPL"
fi

batch_failures=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    batch_failures=$((batch_failures + 1))
  fi
done
if (( batch_failures > 0 )); then
  echo "WARNING: $batch_failures Batch evaluator process(es) reported invalid rows" >&2
fi

RB_FINAL="$RB"
RB_REPROCESSED="$WORK/recovery_behavior_reprocessed.jsonl"
if [[ -d "$WORK/rb_batch" ]]; then
  if ! persona_redteam/.venv/bin/python official_evaluation/reprocess_rb_batches.py \
    --input "$INPUT" --work-dir "$WORK/rb_batch" \
    --output "$RB_REPROCESSED" --retry-input "$WORK/rb_retry_input.jsonl" \
    --model gpt-4o-mini-2024-07-18; then
    echo "WARNING: some R/B rows still require an explicit retry" >&2
  fi
  RB_FINAL="$RB_REPROCESSED"
fi

aggregate_args=(
  --input "$INPUT" --harmbench "$HB" --cares "$CARES" --judge "$PCSA"
  --b3 "$RB_FINAL" --output "$WORK/summary.json" --csv "$WORK/summary.csv"
  --allow-incomplete
)
if [[ -s "$PPL" ]]; then
  aggregate_args+=(--perplexity "$PPL")
fi
persona_redteam/.venv/bin/python official_evaluation/aggregate_pilot.py \
  "${aggregate_args[@]}"

if ! persona_redteam/.venv/bin/python official_evaluation/aggregate_strict_joint.py \
  --input "$INPUT" --rb "$RB_FINAL" --harmbench "$HB" \
  --output "$WORK/strict_joint_summary.json" \
  --csv "$WORK/strict_joint_summary.csv" \
  --joined "$WORK/strict_joint_joined.jsonl"; then
  echo "WARNING: strict-joint summary contains missing or invalid rows" >&2
fi

echo "PCSA Final-197 evaluation complete: condition=$PCSA_CONDITION work=$WORK"

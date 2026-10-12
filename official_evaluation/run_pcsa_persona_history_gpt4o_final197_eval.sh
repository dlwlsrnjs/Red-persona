#!/usr/bin/env bash
# Evaluate the GPT-4o PCSA Persona+History Final-197 cell after all three
# generation shards are complete. OpenAI judges use Batch; HarmBench is local.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

: "${OPENAI_API_KEY:?OPENAI_API_KEY must be exported before execution}"

EVAL_PYTHON="${EVAL_PYTHON:-$REPO_ROOT/persona_redteam/.venv/bin/python}"
ROOT="${ROOT:-external_baselines/outputs/pcsa_persona_history_final197/gpt4o/pcsa_phase2}"
WORK="${WORK:-official_evaluation/work/pcsa_persona_history_gpt4o_final197}"
HARM_BENCH_GPU="${HARM_BENCH_GPU:-0}"

if [[ ! -x "$EVAL_PYTHON" ]]; then
  echo "Evaluation Python is missing: $EVAL_PYTHON" >&2
  echo "Set EVAL_PYTHON to an environment with torch, transformers, and openai." >&2
  exit 1
fi

INPUT="$WORK/input.jsonl"
HB="$WORK/harmbench.jsonl"
CARES="$WORK/cares_gpt4o.jsonl"
PCSA="$WORK/pcsa_figure4_gpt4o.jsonl"
RB="$WORK/recovery_behavior.jsonl"
mkdir -p "$WORK"

"$EVAL_PYTHON" official_evaluation/prepare_single_baseline_cell.py \
  --input-dir "$ROOT/shard-0" \
  --input-dir "$ROOT/shard-1" \
  --input-dir "$ROOT/shard-2" \
  --target-model gpt4o \
  --method pcsa_phase2_persona_history \
  --row-prefix final197-persona-history-gpt4o \
  --output "$INPUT"

pids=()
"$EVAL_PYTHON" official_evaluation/evaluate_cares.py \
  --input "$INPUT" --output "$CARES" --mode batch \
  --model gpt-4o-2024-11-20 --poll-seconds 30 \
  --work-dir "$WORK/cares_gpt4o_batch" &
pids+=("$!")

"$EVAL_PYTHON" official_evaluation/evaluate_pcsa_gpt4o_judge.py \
  --input "$INPUT" --output "$PCSA" --work-dir "$WORK/pcsa_gpt4o_batch" \
  --model gpt-4o-2024-11-20 --target-field goal --poll-seconds 30 &
pids+=("$!")

"$EVAL_PYTHON" official_evaluation/evaluate_b3_behavior.py \
  --input "$INPUT" --output "$RB" --work-dir "$WORK/rb_batch" \
  --model gpt-4o-mini-2024-07-18 --poll-seconds 30 &
pids+=("$!")

CUDA_VISIBLE_DEVICES="$HARM_BENCH_GPU" HF_HUB_OFFLINE=1 \
  "$EVAL_PYTHON" official_evaluation/evaluate_harmbench.py \
    --input "$INPUT" --output "$HB" --device-map cuda:0 --batch-size 16

batch_failures=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    batch_failures=$((batch_failures + 1))
  fi
done
if (( batch_failures > 0 )); then
  echo "WARNING: $batch_failures Batch evaluator process(es) returned invalid rows; applying saved-output reprocessing" >&2
fi

RB_FINAL="$RB"
RB_REPROCESSED="$WORK/recovery_behavior_reprocessed.jsonl"
if [[ -d "$WORK/rb_batch" ]]; then
  "$EVAL_PYTHON" official_evaluation/reprocess_rb_batches.py \
    --input "$INPUT" --work-dir "$WORK/rb_batch" \
    --output "$RB_REPROCESSED" --retry-input "$WORK/rb_retry_input.jsonl" \
    --model gpt-4o-mini-2024-07-18
  RB_FINAL="$RB_REPROCESSED"
fi

"$EVAL_PYTHON" official_evaluation/aggregate_pilot.py \
  --input "$INPUT" --harmbench "$HB" --cares "$CARES" --judge "$PCSA" \
  --b3 "$RB_FINAL" --output "$WORK/summary.json" --csv "$WORK/summary.csv"

"$EVAL_PYTHON" official_evaluation/aggregate_strict_joint.py \
  --input "$INPUT" --rb "$RB_FINAL" --harmbench "$HB" \
  --output "$WORK/strict_joint_summary.json" \
  --csv "$WORK/strict_joint_summary.csv" \
  --joined "$WORK/strict_joint_joined.jsonl"

echo "PCSA Persona+History GPT-4o Final-197 evaluation complete: $WORK"

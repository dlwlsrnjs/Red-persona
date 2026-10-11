#!/usr/bin/env bash
#SBATCH --job-name=final197-eval
#SBATCH --partition=h200
#SBATCH --gres=gpu:7
#SBATCH --cpus-per-task=56
#SBATCH --mem=224G
#SBATCH --time=24:00:00
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

WORK="official_evaluation/work/final197"
INPUT="$WORK/input.jsonl"
PENDING="$WORK/pending_input.jsonl"
RB_PENDING="$WORK/rb_pending154.jsonl"
HB_PENDING="$WORK/harmbench_pending154.jsonl"
RB="$WORK/rb_all197.jsonl"
HB="$WORK/harmbench_all197.jsonl"
mkdir -p "$WORK/harmbench_shards"

persona_redteam/.venv/bin/python official_evaluation/prepare_final_matrix.py \
  --input-dir external_baselines/outputs/final197 \
  --cohort-index external_baselines/data/final197/final197_cohort.jsonl \
  --row-prefix final197 \
  --output "$INPUT"

persona_redteam/.venv/bin/python official_evaluation/prepare_final197_eval_reuse.py \
  --input "$INPUT" \
  --reuse-map external_baselines/data/final197/reuse43_mapping.json \
  --old-rb official_evaluation/work/strict_joint_62_rb.jsonl \
  --old-harmbench official_evaluation/work/strict_joint_62_harmbench.jsonl \
  --output-dir "$WORK"

# Evaluate only the 154 cases without reusable decisions: 2 targets x 9 methods.
pids=()
for shard in $(seq 0 6); do
  CUDA_VISIBLE_DEVICES="$shard" persona_redteam/.venv/bin/python \
    official_evaluation/evaluate_harmbench.py \
    --input "$PENDING" \
    --output "$WORK/harmbench_shards/shard-${shard}.jsonl" \
    --num-shards 7 \
    --shard-index "$shard" \
    --device-map cuda:0 \
    --batch-size 16 &
  pids+=("$!")
done
for pid in "${pids[@]}"; do
  wait "$pid"
done
cat "$WORK"/harmbench_shards/shard-*.jsonl > "$HB_PENDING"

persona_redteam/.venv/bin/python official_evaluation/evaluate_b3_behavior.py \
  --input "$PENDING" \
  --output "$RB_PENDING" \
  --work-dir "$WORK/rb_batch" \
  --model gpt-4o-mini \
  --poll-seconds 30

cat "$WORK/seeded_rb.jsonl" "$RB_PENDING" > "$RB"
cat "$WORK/seeded_harmbench.jsonl" "$HB_PENDING" > "$HB"

persona_redteam/.venv/bin/python official_evaluation/aggregate_strict_joint.py \
  --input "$INPUT" \
  --rb "$RB" \
  --harmbench "$HB" \
  --output "$WORK/strict_joint_summary.json" \
  --csv "$WORK/strict_joint_summary.csv" \
  --joined "$WORK/strict_joint_joined.jsonl"

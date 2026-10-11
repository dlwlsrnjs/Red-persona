#!/usr/bin/env bash
#SBATCH --job-name=f197-hb-half
#SBATCH --partition=h200
#SBATCH --gres=gpu:7
#SBATCH --cpus-per-task=56
#SBATCH --mem=224G
#SBATCH --time=08:00:00
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

: "${SHARD_OFFSET:?SHARD_OFFSET must be set}"
TOTAL_SHARDS="${TOTAL_SHARDS:-14}"
LOCAL_GPU_COUNT="${LOCAL_GPU_COUNT:-7}"
WORK="official_evaluation/work/final197"
PENDING="$WORK/pending_input.jsonl"
SHARD_DIR="$WORK/harmbench_shards14"
mkdir -p "$SHARD_DIR"

pids=()
for local_gpu in $(seq 0 $((LOCAL_GPU_COUNT - 1))); do
  global_shard=$((SHARD_OFFSET + local_gpu))
  CUDA_VISIBLE_DEVICES="$local_gpu" persona_redteam/.venv/bin/python \
    official_evaluation/evaluate_harmbench.py \
    --input "$PENDING" \
    --output "$SHARD_DIR/shard-$(printf '%02d' "$global_shard").jsonl" \
    --num-shards "$TOTAL_SHARDS" \
    --shard-index "$global_shard" \
    --device-map cuda:0 \
    --batch-size 16 &
  pids+=("$!")
done

for pid in "${pids[@]}"; do
  wait "$pid"
done

echo "harmbench half complete: offset=$SHARD_OFFSET count=$LOCAL_GPU_COUNT total=$TOTAL_SHARDS"

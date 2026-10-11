#!/usr/bin/env bash
#SBATCH --job-name=pcsa-ph-197
#SBATCH --partition=h200
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=48:00:00
#SBATCH --array=0-1%2

# Two disjoint shards of the Final-197 PCSA persona-history experiment.
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY must be exported before submission" >&2
  exit 1
fi

export RED_PERSONA_VENV="${RED_PERSONA_VENV:-$REPO_ROOT/persona_redteam/.venv}"
export HF_HOME="${HF_HOME:-/home/ljk98/POLY/hf-cache}"
export HF_HUB_OFFLINE=1
export QWEN_TARGET_API_KEY=local
export QWEN_ADVERSARY_API_KEY=local

TOTAL_CASES=197
SHARD_COUNT=2
SHARD_INDEX="${SLURM_ARRAY_TASK_ID:?submit this script as its declared array}"
BASE_SIZE=$((TOTAL_CASES / SHARD_COUNT))
REMAINDER=$((TOTAL_CASES % SHARD_COUNT))
if (( SHARD_INDEX < REMAINDER )); then
  SHARD_SIZE=$((BASE_SIZE + 1))
  SHARD_START=$((SHARD_INDEX * SHARD_SIZE))
else
  SHARD_SIZE=$BASE_SIZE
  SHARD_START=$((REMAINDER * (BASE_SIZE + 1) + (SHARD_INDEX - REMAINDER) * BASE_SIZE))
fi
SHARD_STOP=$((SHARD_START + SHARD_SIZE))

mkdir -p serve_logs external_baselines/outputs
SERVER_LOG="serve_logs/pcsa-persona-history-final197-${SLURM_ARRAY_JOB_ID}-${SHARD_INDEX}.log"
setsid env QWEN_SERVE_GPU=0 QWEN_SERVE_PORT=8000 \
  bash serve_models.sh qwen >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill -- -"$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

READY=0
for _ in $(seq 1 240); do
  if curl --silent --fail --max-time 2 http://127.0.0.1:8000/v1/models >/dev/null; then
    READY=1
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "Qwen server exited during startup; see $SERVER_LOG" >&2
    exit 1
  fi
  sleep 2
done
if [[ "$READY" != 1 ]]; then
  echo "Qwen server did not become ready within 480 seconds; see $SERVER_LOG" >&2
  exit 1
fi

OUTPUT_DIR="external_baselines/outputs/pcsa_persona_history_final197/qwen7b_instruct/pcsa_phase2/shard-${SHARD_INDEX}"
external_baselines/.venv/bin/python external_baselines/run_pyrit_baseline.py \
  --method pcsa_phase2 \
  --input external_baselines/data/final197/final197_goals.jsonl \
  --cohort-index external_baselines/data/final197/final197_cohort.jsonl \
  --pathology-routes external_baselines/data/final197/final197_pathology_routes.jsonl \
  --pcsa-persona-history persona_redteam/our_method/data/FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL.json \
  --start "$SHARD_START" \
  --stop "$SHARD_STOP" \
  --seed 19701 \
  --max-turns 4 \
  --pcsa-candidates 4 \
  --target-endpoint http://127.0.0.1:8000/v1 \
  --target-model Qwen/Qwen2.5-7B-Instruct \
  --target-api-key-env QWEN_TARGET_API_KEY \
  --adversary-endpoint http://127.0.0.1:8000/v1 \
  --adversary-model Qwen/Qwen2.5-7B-Instruct \
  --adversary-api-key-env QWEN_ADVERSARY_API_KEY \
  --pcsa-evaluator-endpoint https://api.openai.com/v1 \
  --pcsa-evaluator-model gpt-4o-mini-2024-07-18 \
  --pcsa-evaluator-api-key-env OPENAI_API_KEY \
  --pcsa-evaluator-transport openai_batch \
  --sync-case-concurrency 64 \
  --batch-case-concurrency 64 \
  --output-dir "$OUTPUT_DIR"

echo "PCSA persona-history Final-197 shard complete: index=$SHARD_INDEX range=[$SHARD_START,$SHARD_STOP) output=$OUTPUT_DIR"

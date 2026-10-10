#!/usr/bin/env bash
#SBATCH --job-name=luna-llama-p10
#SBATCH --partition=h200
#SBATCH --gres=gpu:7
#SBATCH --cpus-per-task=64
#SBATCH --mem=256G
#SBATCH --time=24:00:00
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY must be exported before sbatch submission" >&2
  exit 1
fi

export RED_PERSONA_VENV="${RED_PERSONA_VENV:-$REPO_ROOT/persona_redteam/.venv}"
export HF_HOME="${HF_HOME:-/home/ljk98/POLY/hf-cache}"
export HF_HUB_OFFLINE=1
export QWEN_ADVERSARY_API_KEY="${QWEN_ADVERSARY_API_KEY:-local}"
export LLAMA_TARGET_API_KEY="${LLAMA_TARGET_API_KEY:-local}"

mkdir -p serve_logs external_baselines/outputs external_baselines/evaluations
IFS=',' read -r -a GPU_IDS <<<"${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6}"
if (( ${#GPU_IDS[@]} < 7 )); then
  echo "This pilot requires seven allocated GPUs" >&2
  exit 1
fi

SERVER_PIDS=()
SERVER_LOGS=()
QWEN_ENDPOINTS=()

LLAMA_LOG="serve_logs/llama31-${SLURM_JOB_ID:-manual}.log"
setsid env LLAMA_SERVE_GPU="${GPU_IDS[0]}" LLAMA_SERVE_PORT=8100 \
  bash serve_models.sh llama >"$LLAMA_LOG" 2>&1 &
SERVER_PIDS+=("$!")
SERVER_LOGS+=("$LLAMA_LOG")

for ((index = 0; index < 6; index++)); do
  port=$((8000 + index))
  log="serve_logs/qwen-luna-llama-${SLURM_JOB_ID:-manual}-${index}.log"
  setsid env QWEN_SERVE_GPU="${GPU_IDS[$((index + 1))]}" QWEN_SERVE_PORT="$port" \
    bash serve_models.sh qwen >"$log" 2>&1 &
  SERVER_PIDS+=("$!")
  SERVER_LOGS+=("$log")
  QWEN_ENDPOINTS+=("http://127.0.0.1:${port}/v1")
done

cleanup() {
  for pid in "${SERVER_PIDS[@]}"; do kill -- -"$pid" 2>/dev/null || true; done
  for pid in "${SERVER_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

ENDPOINTS=("http://127.0.0.1:8100/v1" "${QWEN_ENDPOINTS[@]}")
for _ in $(seq 1 240); do
  ready=1
  for endpoint in "${ENDPOINTS[@]}"; do
    curl --silent --fail --max-time 2 "$endpoint/models" >/dev/null || ready=0
  done
  [[ "$ready" == 1 ]] && break
  sleep 2
done
for endpoint in "${ENDPOINTS[@]}"; do
  curl --silent --fail --max-time 5 "$endpoint/models" >/dev/null
done

external_baselines/.venv/bin/python -m pytest -q external_baselines/tests

OUTPUT_ROOT="${MATRIX_OUTPUT_ROOT:-external_baselines/outputs/gpt6_luna_llama31_pilot10}"
MATRIX_ARGS=(
  --config external_baselines/matrix_gpt6_luna_llama.json
  --output-dir "$OUTPUT_ROOT"
  --pilot-cases "${PILOT_CASES:-10}"
  --max-concurrent-jobs 18
  --job-retries 2
)
for endpoint in "${QWEN_ENDPOINTS[@]}"; do
  MATRIX_ARGS+=(--qwen-endpoint "$endpoint")
done
external_baselines/.venv/bin/python external_baselines/run_baseline_matrix.py \
  "${MATRIX_ARGS[@]}"

external_baselines/.venv/bin/python external_baselines/evaluate_cares_jmir.py \
  --input-root "$OUTPUT_ROOT" \
  --output-dir external_baselines/evaluations/gpt6_luna_llama31_pilot10 \
  --expected-cases "${PILOT_CASES:-10}" \
  --api-mode batch \
  --max-budget-usd 2 \
  --poll-seconds 30 \
  --execute

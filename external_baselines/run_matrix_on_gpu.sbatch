#!/usr/bin/env bash
#SBATCH --job-name=redpersona-9x2
#SBATCH --partition=h200
#SBATCH --gres=gpu:7
#SBATCH --cpus-per-task=64
#SBATCH --mem=256G
#SBATCH --time=48:00:00

# Start one Qwen vLLM replica per allocated GPU, then distribute all nine
# methods against Qwen and GPT-4o across the replica pool. Submit from the root:
#   sbatch external_baselines/run_matrix_on_gpu.sbatch
# Optional:
#   PILOT_CASES=2 sbatch external_baselines/run_matrix_on_gpu.sbatch
#   FULL_500=1 sbatch external_baselines/run_matrix_on_gpu.sbatch
#   QWEN_REPLICAS=4 sbatch --gres=gpu:4 external_baselines/run_matrix_on_gpu.sbatch
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

if [[ ! -x external_baselines/.venv/bin/python ]]; then
  echo "Missing external_baselines/.venv; run bash external_baselines/setup_env.sh" >&2
  exit 1
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY must be exported before sbatch submission" >&2
  exit 1
fi

export RED_PERSONA_VENV="${RED_PERSONA_VENV:-$REPO_ROOT/persona_redteam/.venv}"
export HF_HOME="${HF_HOME:-/home/ljk98/POLY/hf-cache}"
export HF_HUB_OFFLINE=1
export QWEN_TARGET_API_KEY="${QWEN_TARGET_API_KEY:-local}"
export QWEN_ADVERSARY_API_KEY="${QWEN_ADVERSARY_API_KEY:-local}"

mkdir -p serve_logs external_baselines/outputs

if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  IFS=',' read -r -a GPU_IDS <<<"$CUDA_VISIBLE_DEVICES"
else
  GPU_IDS=(0 1 2 3 4 5 6)
fi
REPLICA_COUNT="${QWEN_REPLICAS:-${#GPU_IDS[@]}}"
if ! [[ "$REPLICA_COUNT" =~ ^[1-9][0-9]*$ ]]; then
  echo "QWEN_REPLICAS must be a positive integer" >&2
  exit 1
fi
if (( REPLICA_COUNT > ${#GPU_IDS[@]} )); then
  echo "Requested $REPLICA_COUNT Qwen replicas but only ${#GPU_IDS[@]} GPUs are allocated" >&2
  exit 1
fi

SERVER_PIDS=()
SERVER_LOGS=()
QWEN_ENDPOINTS=()
for ((index = 0; index < REPLICA_COUNT; index++)); do
  port=$((8000 + index))
  endpoint="http://127.0.0.1:${port}/v1"
  log="serve_logs/qwen-${SLURM_JOB_ID:-manual}-replica-${index}.log"
  setsid env \
    QWEN_SERVE_GPU="${GPU_IDS[$index]}" \
    QWEN_SERVE_PORT="$port" \
    bash serve_models.sh qwen >"$log" 2>&1 &
  SERVER_PIDS+=("$!")
  SERVER_LOGS+=("$log")
  QWEN_ENDPOINTS+=("$endpoint")
done

cleanup() {
  for pid in "${SERVER_PIDS[@]}"; do
    kill -- -"$pid" 2>/dev/null || true
  done
  for pid in "${SERVER_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

READY=0
for _ in $(seq 1 240); do
  ALL_READY=1
  for index in "${!QWEN_ENDPOINTS[@]}"; do
    if ! kill -0 "${SERVER_PIDS[$index]}" 2>/dev/null; then
      echo "Qwen replica $index exited during startup; see ${SERVER_LOGS[$index]}" >&2
      exit 1
    fi
    if ! curl --silent --fail --max-time 2 "${QWEN_ENDPOINTS[$index]}/models" >/dev/null; then
      ALL_READY=0
    fi
  done
  if [[ "$ALL_READY" == 1 ]]; then
    READY=1
    break
  fi
  sleep 2
done
if [[ "$READY" != 1 ]]; then
  echo "Not all Qwen replicas became ready within 480 seconds" >&2
  exit 1
fi
echo "Ready Qwen replicas: ${QWEN_ENDPOINTS[*]}"

external_baselines/.venv/bin/python -m pytest -q external_baselines/tests

OUTPUT_ROOT="external_baselines/outputs/qwen_gpt4o_${SLURM_JOB_ID:-manual}"
MATRIX_ARGS=(
  --output-dir "$OUTPUT_ROOT"
  --max-concurrent-jobs "${MATRIX_MAX_JOBS:-18}"
)
for endpoint in "${QWEN_ENDPOINTS[@]}"; do
  MATRIX_ARGS+=(--qwen-endpoint "$endpoint")
done
if [[ "${FULL_500:-0}" == 1 ]]; then
  MATRIX_ARGS+=(--full-500)
else
  MATRIX_ARGS+=(--pilot-cases "${PILOT_CASES:-1}")
fi

external_baselines/.venv/bin/python external_baselines/run_baseline_matrix.py \
  "${MATRIX_ARGS[@]}"

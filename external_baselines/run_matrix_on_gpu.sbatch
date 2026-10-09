#!/usr/bin/env bash
#SBATCH --job-name=redpersona-9x2
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=48:00:00

# Start one shared Qwen vLLM endpoint on the allocated GPU, then run all nine
# methods against Qwen and GPT-4o. Submit from the repository root:
#   sbatch external_baselines/run_matrix_on_gpu.sbatch
# Optional:
#   PILOT_CASES=2 sbatch external_baselines/run_matrix_on_gpu.sbatch
#   FULL_500=1 sbatch external_baselines/run_matrix_on_gpu.sbatch
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
SERVER_LOG="serve_logs/qwen-${SLURM_JOB_ID:-manual}.log"
setsid bash serve_models.sh qwen >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill -- -"$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

READY=0
for _ in $(seq 1 180); do
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
  echo "Qwen server did not become ready within 360 seconds; see $SERVER_LOG" >&2
  exit 1
fi

external_baselines/.venv/bin/python -m pytest -q external_baselines/tests

OUTPUT_ROOT="external_baselines/outputs/qwen_gpt4o_${SLURM_JOB_ID:-manual}"
MATRIX_ARGS=(
  --output-dir "$OUTPUT_ROOT"
  --max-concurrent-jobs "${MATRIX_MAX_JOBS:-18}"
)
if [[ "${FULL_500:-0}" == 1 ]]; then
  MATRIX_ARGS+=(--full-500)
else
  MATRIX_ARGS+=(--pilot-cases "${PILOT_CASES:-1}")
fi

external_baselines/.venv/bin/python external_baselines/run_baseline_matrix.py \
  "${MATRIX_ARGS[@]}"

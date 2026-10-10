#!/usr/bin/env bash
#SBATCH --job-name=luna-llama-500
#SBATCH --partition=h200
#SBATCH --gres=gpu:7
#SBATCH --cpus-per-task=64
#SBATCH --mem=256G
#SBATCH --time=48:00:00
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY must be exported before sbatch submission" >&2
  exit 1
fi
if [[ -z "${CASE_START:-}" || -z "${CASE_COUNT:-}" || -z "${SHARD_NAME:-}" ]]; then
  echo "CASE_START, CASE_COUNT, and SHARD_NAME are required" >&2
  exit 1
fi
if (( CASE_START < 0 || CASE_COUNT < 1 || CASE_START + CASE_COUNT > 500 )); then
  echo "invalid shard bounds: start=$CASE_START count=$CASE_COUNT" >&2
  exit 1
fi
if [[ ! "$SHARD_NAME" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "SHARD_NAME contains unsupported characters" >&2
  exit 1
fi

export RED_PERSONA_VENV="${RED_PERSONA_VENV:-$REPO_ROOT/persona_redteam/.venv}"
export HF_HOME="${HF_HOME:-/home/ljk98/POLY/hf-cache}"
export HF_HUB_OFFLINE=1
export QWEN_ADVERSARY_API_KEY="${QWEN_ADVERSARY_API_KEY:-local}"
export LLAMA_TARGET_API_KEY="${LLAMA_TARGET_API_KEY:-local}"

FULL_ROOT="${FULL_OUTPUT_ROOT:-external_baselines/outputs/gpt6_luna_llama31_full500}"
OUTPUT_ROOT="${SHARD_OUTPUT_ROOT:-$FULL_ROOT/shards/$SHARD_NAME}"
mkdir -p serve_logs "$OUTPUT_ROOT"

IFS=',' read -r -a GPU_IDS <<<"${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6}"
if (( ${#GPU_IDS[@]} < 2 )); then
  echo "at least two allocated GPUs are required" >&2
  exit 1
fi

SERVER_PIDS=()
QWEN_ENDPOINTS=()

LLAMA_LOG="serve_logs/llama31-full-${SHARD_NAME}-${SLURM_JOB_ID:-manual}.log"
setsid env LLAMA_SERVE_GPU="${GPU_IDS[0]}" LLAMA_SERVE_PORT=8100 \
  bash serve_models.sh llama >"$LLAMA_LOG" 2>&1 &
SERVER_PIDS+=("$!")

for ((index = 1; index < ${#GPU_IDS[@]}; index++)); do
  port=$((7999 + index))
  log="serve_logs/qwen-full-${SHARD_NAME}-${SLURM_JOB_ID:-manual}-${index}.log"
  setsid env QWEN_SERVE_GPU="${GPU_IDS[$index]}" QWEN_SERVE_PORT="$port" \
    bash serve_models.sh qwen >"$log" 2>&1 &
  SERVER_PIDS+=("$!")
  QWEN_ENDPOINTS+=("http://127.0.0.1:${port}/v1")
done

cleanup() {
  for pid in "${SERVER_PIDS[@]}"; do kill -- -"$pid" 2>/dev/null || true; done
  for pid in "${SERVER_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

ENDPOINTS=("http://127.0.0.1:8100/v1" "${QWEN_ENDPOINTS[@]}")
ready=0
for _ in $(seq 1 300); do
  ready=1
  for endpoint in "${ENDPOINTS[@]}"; do
    curl --silent --fail --max-time 2 "$endpoint/models" >/dev/null || ready=0
  done
  [[ "$ready" == 1 ]] && break
  sleep 2
done
if [[ "$ready" != 1 ]]; then
  echo "one or more model endpoints did not become ready" >&2
  exit 1
fi

MATRIX_ARGS=(
  --config external_baselines/matrix_gpt6_luna_llama.json
  --output-dir "$OUTPUT_ROOT"
  --case-start "$CASE_START"
  --pilot-cases "$CASE_COUNT"
  --max-concurrent-jobs 18
  --job-retries 2
  --run-label "$SHARD_NAME"
)
for endpoint in "${QWEN_ENDPOINTS[@]}"; do
  MATRIX_ARGS+=(--qwen-endpoint "$endpoint")
done

external_baselines/.venv/bin/python external_baselines/run_baseline_matrix.py \
  "${MATRIX_ARGS[@]}"

external_baselines/.venv/bin/python - "$OUTPUT_ROOT" "$CASE_COUNT" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
expected = int(sys.argv[2])
manifests = sorted(root.glob("*/*/run_summary.json"))
if len(manifests) != 18:
    raise SystemExit(f"expected 18 completed cells, found {len(manifests)}")
for path in manifests:
    summary = json.loads(path.read_text(encoding="utf-8"))
    checkpoints = summary.get("checkpoints") or {}
    if checkpoints.get("completed") != expected or not checkpoints.get("is_complete"):
        raise SystemExit(f"incomplete shard cell: {path}")
(root / "SHARD_COMPLETE").write_text("complete\n", encoding="utf-8")
PY

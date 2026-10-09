#!/usr/bin/env bash
#SBATCH --job-name=qwen-pool-smoke
#SBATCH --partition=h200
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=24
#SBATCH --mem=96G
#SBATCH --time=00:20:00

# Validate that distinct baseline processes can use separate Qwen replicas at
# the same time. This requires no external API key and writes only ignored
# smoke-test outputs.
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

export RED_PERSONA_VENV="${RED_PERSONA_VENV:-$REPO_ROOT/persona_redteam/.venv}"
export HF_HOME="${HF_HOME:-/home/ljk98/POLY/hf-cache}"
export HF_HUB_OFFLINE=1
export QWEN_TARGET_API_KEY=local
export QWEN_ADVERSARY_API_KEY=local

if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  IFS=',' read -r -a GPU_IDS <<<"$CUDA_VISIBLE_DEVICES"
else
  GPU_IDS=(0 1)
fi
if (( ${#GPU_IDS[@]} < 2 )); then
  echo "The pool smoke test requires two allocated GPUs" >&2
  exit 1
fi

mkdir -p serve_logs external_baselines/outputs
SERVER_PIDS=()
ENDPOINTS=("http://127.0.0.1:8000/v1" "http://127.0.0.1:8001/v1")
for index in 0 1; do
  setsid env \
    QWEN_SERVE_GPU="${GPU_IDS[$index]}" \
    QWEN_SERVE_PORT="$((8000 + index))" \
    bash serve_models.sh qwen \
    >"serve_logs/qwen-pool-${SLURM_JOB_ID:-manual}-${index}.log" 2>&1 &
  SERVER_PIDS+=("$!")
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
  for index in 0 1; do
    if ! kill -0 "${SERVER_PIDS[$index]}" 2>/dev/null; then
      echo "Qwen replica $index exited during startup" >&2
      exit 1
    fi
    if ! curl --silent --fail --max-time 2 "${ENDPOINTS[$index]}/models" >/dev/null; then
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
  echo "Qwen replica pool did not become ready within 480 seconds" >&2
  exit 1
fi

OUTPUT_ROOT="external_baselines/outputs/qwen_pool_smoke_${SLURM_JOB_ID:-manual}"
mkdir -p "$OUTPUT_ROOT"

external_baselines/.venv/bin/python external_baselines/run_pyrit_baseline.py \
  --method direct \
  --limit 4 \
  --sync-case-concurrency 4 \
  --target-endpoint "${ENDPOINTS[0]}" \
  --target-model Qwen/Qwen2.5-7B-Instruct \
  --target-api-key-env QWEN_TARGET_API_KEY \
  --output-dir "$OUTPUT_ROOT/direct" \
  >"$OUTPUT_ROOT/direct.log" 2>&1 &
DIRECT_PID=$!

external_baselines/.venv/bin/python external_baselines/run_pyrit_baseline.py \
  --method red_teaming \
  --limit 2 \
  --max-turns 2 \
  --sync-case-concurrency 2 \
  --target-endpoint "${ENDPOINTS[1]}" \
  --target-model Qwen/Qwen2.5-7B-Instruct \
  --target-api-key-env QWEN_TARGET_API_KEY \
  --adversary-endpoint "${ENDPOINTS[1]}" \
  --adversary-model Qwen/Qwen2.5-7B-Instruct \
  --adversary-api-key-env QWEN_ADVERSARY_API_KEY \
  --output-dir "$OUTPUT_ROOT/red_teaming" \
  >"$OUTPUT_ROOT/red_teaming.log" 2>&1 &
RED_TEAMING_PID=$!

DIRECT_STATUS=0
RED_TEAMING_STATUS=0
wait "$DIRECT_PID" || DIRECT_STATUS=$?
wait "$RED_TEAMING_PID" || RED_TEAMING_STATUS=$?
if (( DIRECT_STATUS != 0 || RED_TEAMING_STATUS != 0 )); then
  echo "Parallel baselines failed: direct=$DIRECT_STATUS red_teaming=$RED_TEAMING_STATUS" >&2
  exit 1
fi

external_baselines/.venv/bin/python - "$OUTPUT_ROOT" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
expected = {"direct": 4, "red_teaming": 2}
for method, count in expected.items():
    summary = json.loads((root / method / "run_summary.json").read_text())
    assert summary["complete"] == count
    assert summary["failed"] == 0
print(json.dumps({"status": "passed", "replicas": 2, "baselines": expected}))
PY

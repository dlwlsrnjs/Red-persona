#!/usr/bin/env bash
#SBATCH --job-name=target-pilot40
#SBATCH --partition=h200
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=32
#SBATCH --mem=192G
#SBATCH --time=48:00:00
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"
STAGE="${PILOT_STAGE:-prepare}"
ARTIFACT_ROOT="${PILOT_ARTIFACT_ROOT:-$REPO_ROOT/persona_redteam/data/target_model_pilot40}"
PY="$REPO_ROOT/persona_redteam/.venv/bin/python"
HF_HOME="${HF_HOME:-/home/ljk98/POLY/hf-cache}"
QWEN_SNAPSHOT="$HF_HOME/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28"
SELECTION="$REPO_ROOT/persona_redteam/ablation/TARGET_MODEL_PILOT40.json"
PREPARED="$ARTIFACT_ROOT/prepared/history_cases.json"
EXECUTION_SELECTION="$ARTIFACT_ROOT/prepared/execution_selection.json"

test -x "$PY"
mkdir -p "$ARTIFACT_ROOT" "$REPO_ROOT/serve_logs"
export HF_HOME HF_HUB_OFFLINE=1 RED_PERSONA_VENV="$REPO_ROOT/persona_redteam/.venv"

if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  IFS=',' read -r -a GPU_IDS <<<"$CUDA_VISIBLE_DEVICES"
else
  GPU_IDS=(0 1)
fi

SERVER_PIDS=()
cleanup() {
  for pid in "${SERVER_PIDS[@]}"; do kill -- -"$pid" 2>/dev/null || true; done
  for pid in "${SERVER_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

start_server() {
  local role="$1" gpu="$2" port="$3" log="$4"
  if [[ "$role" == qwen ]]; then
    setsid env QWEN_SERVE_GPU="$gpu" QWEN_SERVE_PORT="$port" \
      bash serve_models.sh qwen >"$log" 2>&1 &
  elif [[ "$role" == lexi ]]; then
    setsid env LEXI_SERVE_GPU="$gpu" \
      bash serve_models.sh lexi >"$log" 2>&1 &
  else
    setsid env LLAMA_SERVE_GPU="$gpu" LLAMA_SERVE_PORT="$port" \
      bash serve_models.sh llama >"$log" 2>&1 &
  fi
  SERVER_PIDS+=("$!")
}

wait_endpoint() {
  local endpoint="$1"
  for _ in $(seq 1 240); do
    curl --silent --fail --max-time 2 "$endpoint/models" >/dev/null && return 0
    sleep 2
  done
  return 1
}

if [[ "$STAGE" == prepare ]]; then
  (( ${#GPU_IDS[@]} >= 2 )) || { echo "prepare requires two GPUs" >&2; exit 1; }
  start_server qwen "${GPU_IDS[0]}" 8000 "$REPO_ROOT/serve_logs/pilot40-qwen-${SLURM_JOB_ID}.log"
  start_server lexi "${GPU_IDS[1]}" 8002 "$REPO_ROOT/serve_logs/pilot40-lexi-${SLURM_JOB_ID}.log"
  wait_endpoint http://127.0.0.1:8000/v1
  wait_endpoint http://127.0.0.1:8002/v1
  PYTHONPATH=persona_redteam "$PY" persona_redteam/experiments/prepare_target_model_pilot40.py \
    --cases-output "$ARTIFACT_ROOT/prepared/pre_generation_cases.json" \
    --execution-selection-output "$EXECUTION_SELECTION"
  PYTHONPATH=persona_redteam "$PY" -m pipeline.generate_histories \
    --cases "$ARTIFACT_ROOT/prepared/pre_generation_cases.json" \
    --generation-prompt persona_redteam/configs/persona_history/generation_prompt.template.txt \
    --coverage-prompt persona_redteam/configs/persona_history/coverage_prompt.template.txt \
    --model Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
    --base-url http://127.0.0.1:8002/v1 \
    --qwen-model Qwen/Qwen2.5-7B-Instruct \
    --qwen-base-url http://127.0.0.1:8000/v1 \
    --min-turns 4 --max-turns 12 --generation-attempts 6 \
    --lexi-temperature 0.7 --seed 20261010 \
    --checkpoint-dir "$ARTIFACT_ROOT/prepared/history_checkpoints" \
    --output "$PREPARED" --retry-failed
  exit 0
fi

if [[ "$STAGE" == gpt6_luna || "$STAGE" == llama31_8b ]]; then
  test -n "${OPENAI_API_KEY:-}" || { echo "OPENAI_API_KEY is required" >&2; exit 1; }
  test -f "$PREPARED"
  test -f "$EXECUTION_SELECTION"
  TARGET_MODEL=gpt-6-luna
  TARGET_DIR=gpt6_luna
  TARGET_ARGS=()
  EVAL_TARGET=gpt6_luna
  if [[ "$STAGE" == llama31_8b ]]; then
    (( ${#GPU_IDS[@]} >= 2 )) || { echo "Llama stage requires two GPUs" >&2; exit 1; }
    TARGET_MODEL=meta-llama/Llama-3.1-8B-Instruct
    TARGET_DIR=llama31_8b_instruct
    EVAL_TARGET=llama31_8b
    start_server llama "${GPU_IDS[1]}" 8100 "$REPO_ROOT/serve_logs/pilot40-llama-${SLURM_JOB_ID}.log"
    wait_endpoint http://127.0.0.1:8100/v1
    TARGET_ARGS+=(--target-base-url http://127.0.0.1:8100/v1 --target-workers 64)
  fi
  CUDA_VISIBLE_DEVICES="${GPU_IDS[0]}" PYTHONPATH=persona_redteam "$PY" \
    persona_redteam/experiments/run_jmir_persona_batch_api.py \
    --cases "$PREPARED" \
    --output-dir "$ARTIFACT_ROOT/$TARGET_DIR/runs" \
    --campaign-dir "$ARTIFACT_ROOT/$TARGET_DIR/campaign" \
    --no-research-dialogue-output-dir "$ARTIFACT_ROOT/$TARGET_DIR/no_dialogue_runs" \
    --selection-path "$EXECUTION_SELECTION" --selection-key final_case_ids \
    --target-total 40 --start 0 --stop 40 \
    --target-model "$TARGET_MODEL" --condition neutral \
    --final-readout-protocol jargon_history_bridge_v1 \
    --qwen-snapshot "$QWEN_SNAPSHOT" --max-budget-usd 4 --poll-seconds 30 \
    "${TARGET_ARGS[@]}"
  PYTHONPATH=persona_redteam "$PY" persona_redteam/experiments/evaluate_target_model_pilot40.py \
    --selection "$SELECTION" --artifact-root "$ARTIFACT_ROOT" \
    --output-dir "$ARTIFACT_ROOT/evaluations/$EVAL_TARGET" \
    --public-dir "$REPO_ROOT/persona_redteam/result/target_model_pilot40_parts/$EVAL_TARGET" \
    --targets "$EVAL_TARGET" --max-budget-usd 2 --poll-seconds 30 --execute
  exit 0
fi

if [[ "$STAGE" == combine ]]; then
  PYTHONPATH=persona_redteam "$PY" persona_redteam/experiments/evaluate_target_model_pilot40.py \
    --public-dir "$REPO_ROOT/persona_redteam/result/target_model_pilot40" \
    --combine-public-parts \
    "$REPO_ROOT/persona_redteam/result/target_model_pilot40_parts/gpt6_luna" \
    "$REPO_ROOT/persona_redteam/result/target_model_pilot40_parts/llama31_8b"
  exit 0
fi

echo "Unknown PILOT_STAGE=$STAGE" >&2
exit 2

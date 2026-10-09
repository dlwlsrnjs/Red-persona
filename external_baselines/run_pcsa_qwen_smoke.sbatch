#!/usr/bin/env bash
#SBATCH --job-name=pcsa-qwen-smoke
#SBATCH --partition=h200
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=12
#SBATCH --mem=48G
#SBATCH --time=00:30:00

# End-to-end server smoke test requiring no external API key. It starts the
# pinned Qwen endpoint and runs one PCSA case with four parallel candidates per
# turn and no more than four turns;
# the production matrix still uses GPT-4o-mini as the PCSA evaluator.
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

export RED_PERSONA_VENV="${RED_PERSONA_VENV:-$REPO_ROOT/persona_redteam/.venv}"
export HF_HOME="${HF_HOME:-/home/ljk98/POLY/hf-cache}"
export HF_HUB_OFFLINE=1
export QWEN_TARGET_API_KEY=local
export QWEN_ADVERSARY_API_KEY=local

if [[ ! -x "$RED_PERSONA_VENV/bin/python" ]]; then
  echo "Missing GPU serving environment: $RED_PERSONA_VENV" >&2
  exit 1
fi
if [[ ! -d "$HF_HOME" ]]; then
  echo "Missing Hugging Face cache: $HF_HOME" >&2
  exit 1
fi

mkdir -p serve_logs external_baselines/outputs
SERVER_LOG="serve_logs/qwen-smoke-${SLURM_JOB_ID:-manual}.log"
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

OUTPUT_DIR="external_baselines/outputs/pcsa_qwen_smoke_${SLURM_JOB_ID:-manual}"
external_baselines/.venv/bin/python external_baselines/run_pyrit_baseline.py \
  --method pcsa_phase2 \
  --limit 1 \
  --seed 17 \
  --max-turns 4 \
  --pcsa-candidates 4 \
  --target-endpoint http://127.0.0.1:8000/v1 \
  --target-model Qwen/Qwen2.5-7B-Instruct \
  --target-api-key-env QWEN_TARGET_API_KEY \
  --adversary-endpoint http://127.0.0.1:8000/v1 \
  --adversary-model Qwen/Qwen2.5-7B-Instruct \
  --adversary-api-key-env QWEN_ADVERSARY_API_KEY \
  --pcsa-evaluator-endpoint http://127.0.0.1:8000/v1 \
  --pcsa-evaluator-model Qwen/Qwen2.5-7B-Instruct \
  --pcsa-evaluator-api-key-env QWEN_ADVERSARY_API_KEY \
  --pcsa-evaluator-transport sync \
  --output-dir "$OUTPUT_DIR"

RESULT_FILE="$(find "$OUTPUT_DIR" -maxdepth 1 -type f -name 'jmir-full-*.json' -print -quit)"
if [[ -z "$RESULT_FILE" ]]; then
  echo "No per-case result JSON was produced in $OUTPUT_DIR" >&2
  exit 1
fi
external_baselines/.venv/bin/python - "$RESULT_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    record = json.load(handle)
pcsa = record["internal_attack_control"]["result"]
assert record["method"] == "pcsa_phase2"
assert record["persona_context"]["persona_profile"]
assert record["pathology_context"]["pathology"]
assert pcsa["status"] == "complete"
assert 1 <= pcsa["executed_turns"] <= 4
assert pcsa["candidates_per_turn"] == 4
assert len(pcsa["rounds"]) == pcsa["executed_turns"]
assert all(len(round_["candidates"]) == 4 for round_ in pcsa["rounds"])
assert len(pcsa["target_conversation"]) == 2 * pcsa["executed_turns"]
assert record["final_evaluation"]["status"] == "pending"
PY
echo "PCSA Qwen server smoke test passed: $RESULT_FILE"

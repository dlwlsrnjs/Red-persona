#!/usr/bin/env bash
# Run the Final-197 PCSA Phase-II Persona+History cell against GPT-4o.
#
# GPT-4o target calls and GPT-4o-mini intermediate-judge calls are both sent
# through the OpenAI Batch API.  Only the attacker model is served locally.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

: "${OPENAI_API_KEY:?OPENAI_API_KEY must be exported before execution}"

PYRIT_PYTHON="${PYRIT_PYTHON:-$SCRIPT_DIR/.venv/bin/python}"
QWEN_ENDPOINT="${QWEN_ENDPOINT:-http://127.0.0.1:8000/v1}"
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/outputs/pcsa_persona_history_final197/gpt4o/pcsa_phase2}"
BATCH_CASE_CONCURRENCY="${BATCH_CASE_CONCURRENCY:-197}"
BATCH_POLL_SECONDS="${BATCH_POLL_SECONDS:-30}"
BATCH_FLUSH_SECONDS="${BATCH_FLUSH_SECONDS:-15}"

if [[ ! -x "$PYRIT_PYTHON" ]]; then
  echo "PyRIT Python is missing: $PYRIT_PYTHON" >&2
  echo "Initialize the submodule and run external_baselines/setup_env.sh first." >&2
  exit 1
fi
if ! curl --silent --fail --max-time 5 "$QWEN_ENDPOINT/models" >/dev/null; then
  echo "Local Qwen attacker endpoint is unavailable: $QWEN_ENDPOINT" >&2
  exit 1
fi

export QWEN_ADVERSARY_API_KEY="${QWEN_ADVERSARY_API_KEY:-local}"

exec "$PYRIT_PYTHON" external_baselines/run_pyrit_baseline.py \
  --method pcsa_phase2 \
  --input external_baselines/data/final197/final197_goals.jsonl \
  --cohort-index external_baselines/data/final197/final197_cohort.jsonl \
  --pathology-routes external_baselines/data/final197/final197_pathology_routes.jsonl \
  --pcsa-persona-history persona_redteam/our_method/data/FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL.json \
  --seed 19701 \
  --max-turns 4 \
  --pcsa-candidates 4 \
  --target-endpoint https://api.openai.com/v1 \
  --target-model gpt-4o-2024-11-20 \
  --target-api-key-env OPENAI_API_KEY \
  --target-transport openai_batch \
  --target-temperature 0 \
  --target-max-completion-tokens 4096 \
  --adversary-endpoint "$QWEN_ENDPOINT" \
  --adversary-model Qwen/Qwen2.5-7B-Instruct \
  --adversary-api-key-env QWEN_ADVERSARY_API_KEY \
  --adversary-temperature 0.7 \
  --adversary-max-completion-tokens 4096 \
  --pcsa-evaluator-endpoint https://api.openai.com/v1 \
  --pcsa-evaluator-model gpt-4o-mini-2024-07-18 \
  --pcsa-evaluator-api-key-env OPENAI_API_KEY \
  --pcsa-evaluator-transport openai_batch \
  --pcsa-evaluator-max-completion-tokens 512 \
  --batch-case-concurrency "$BATCH_CASE_CONCURRENCY" \
  --batch-poll-seconds "$BATCH_POLL_SECONDS" \
  --batch-flush-seconds "$BATCH_FLUSH_SECONDS" \
  --batch-request-retries 2 \
  --batch-api-retries 4 \
  --batch-retry-backoff-seconds 5 \
  --output-dir "$OUTPUT_DIR" \
  "$@"

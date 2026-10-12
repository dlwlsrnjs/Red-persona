#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYRIT_PYTHON="${PYRIT_PYTHON:-external_baselines/.venv/bin/python}"
OUTPUT_ROOT="${OUTPUT_ROOT:-external_baselines/outputs/final197_query16_gpt4o_qwen_v1}"

if [[ -n "${OPENAI_ENV_FILE:-}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$OPENAI_ENV_FILE"
  set +a
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is required (or set OPENAI_ENV_FILE)." >&2
  exit 2
fi
if [[ ! -x "$PYRIT_PYTHON" ]]; then
  echo "PyRIT Python is missing: $PYRIT_PYTHON" >&2
  echo "Run bash external_baselines/setup_env.sh first." >&2
  exit 2
fi

QWEN_ARGS=()
for port in 8000 8001 8012 8022; do
  endpoint="http://127.0.0.1:${port}/v1"
  if curl -fsS --max-time 3 "$endpoint/models" >/dev/null; then
    QWEN_ARGS+=(--qwen-endpoint "$endpoint")
  fi
done
if [[ ${#QWEN_ARGS[@]} -eq 0 ]]; then
  echo "No local Qwen endpoint is reachable." >&2
  exit 2
fi

exec "$PYRIT_PYTHON" external_baselines/run_baseline_matrix.py \
  --budget-profile query16 \
  --full-cohort \
  --target-name gpt4o \
  --target-name qwen7b_instruct \
  --input external_baselines/data/final197/final197_goals.jsonl \
  --cohort-index external_baselines/data/final197/final197_cohort.jsonl \
  --persona-map external_baselines/data/final197/final197_persona_assignments.jsonl \
  --pathology-routes external_baselines/data/final197/final197_pathology_routes.jsonl \
  --output-dir "$OUTPUT_ROOT" \
  --run-label final197-query16 \
  --max-concurrent-jobs 6 \
  --adaptive-batch-case-concurrency 128 \
  --method red_teaming \
  --method crescendo \
  --method therapist_crescendo \
  "${QWEN_ARGS[@]}"

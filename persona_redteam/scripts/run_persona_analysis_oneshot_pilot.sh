#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

set -a
# shellcheck disable=SC1091
source configs/llama33_70b_abliterated.env.example
set +a

CLINICAL_CONTEXT_FILE="${CLINICAL_CONTEXT_FILE:-configs/clinical_context.pcsa_v2.json}"

python experiments/persona_analysis_oneshot.py \
  --stage "${STAGE:-generate}" \
  --responder "${RESPONDER:-surrogate}" \
  --context-file "${CLINICAL_CONTEXT_FILE}" \
  --jargon-file "${CLINICAL_JARGON_FILE:-configs/clinical_jargon.example.json}" \
  --per-label "${PER_LABEL:-1}" \
  --surrogate-base-url "${SURROGATE_BASE_URL:-http://127.0.0.1:8017/v1}" \
  --out-dir "${OUT_DIR:-outputs/persona_analysis_oneshot_pilot6}"

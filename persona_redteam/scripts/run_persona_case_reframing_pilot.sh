#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

set -a
# shellcheck disable=SC1091
source configs/llama33_70b_abliterated.env.example
set +a

CLINICAL_CONTEXT_FILE="${CLINICAL_CONTEXT_FILE:-configs/clinical_context.pcsa_v2.json}"

python experiments/persona_case_reframing.py \
  --stage "${STAGE:-search}" \
  --context-file "${CLINICAL_CONTEXT_FILE}" \
  --jargon-file "${CLINICAL_JARGON_FILE:-configs/clinical_jargon.example.json}" \
  --frame-mode "${FRAME_MODE:-direct_counseling}" \
  --per-label "${PER_LABEL:-1}" \
  --rounds "${ROUNDS:-2}" \
  --candidates "${CANDIDATES:-4}" \
  --beam "${BEAM:-4}" \
  --samples-per-candidate "${SAMPLES_PER_CANDIDATE:-5}" \
  --surrogate-base-url "${SURROGATE_BASE_URL:-http://127.0.0.1:8017/v1}" \
  --out-dir "${OUT_DIR:-outputs/persona_case_reframing_optimize_pilot6}"

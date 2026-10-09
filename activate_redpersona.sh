#!/usr/bin/env bash
# Source this file before running the RED-Persona pipeline:
#   source ./activate_redpersona.sh

REDPERSONA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REDPERSONA_ENV="$REDPERSONA_ROOT/.venv"

if [[ ! -x "$REDPERSONA_ENV/bin/python" ]]; then
  echo "Python environment not found: $REDPERSONA_ENV" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1091
source "$REDPERSONA_ENV/bin/activate"

if [[ -f "$REDPERSONA_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REDPERSONA_ROOT/.env"
  set +a
fi

export REDPERSONA_VENV="$REDPERSONA_ENV"
export RED_PERSONA_VENV="$REDPERSONA_ENV"
export HF_HOME="${HF_HOME:-/data1/users/ljk98/hf_cache}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export PERSONA_POOL_PATH="${PERSONA_POOL_PATH:-$REDPERSONA_ROOT/data/personas/personas_enriched.jsonl}"
export PERSONA_CATEGORY_LABELS_PATH="${PERSONA_CATEGORY_LABELS_PATH:-$REDPERSONA_ROOT/data/personas/persona_category_labels.jsonl}"
export QWEN_DEVICE="${QWEN_DEVICE:-cuda:4}"
export QWEN_BATCH_SIZE="${QWEN_BATCH_SIZE:-6}"

echo "RED-Persona environment activated: $REDPERSONA_ROOT"

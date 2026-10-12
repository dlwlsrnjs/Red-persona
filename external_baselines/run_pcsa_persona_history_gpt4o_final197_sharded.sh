#!/usr/bin/env bash
# Use several already-running Qwen endpoints for the local PCSA attacker while
# keeping both OpenAI roles on the Batch API.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

: "${OPENAI_API_KEY:?OPENAI_API_KEY must be exported before execution}"

IFS=',' read -r -a QWEN_ENDPOINTS <<< "${QWEN_ENDPOINTS:-http://127.0.0.1:8000/v1,http://127.0.0.1:8001/v1,http://127.0.0.1:8012/v1}"
TOTAL_CASES=197
SHARD_COUNT="${#QWEN_ENDPOINTS[@]}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$SCRIPT_DIR/outputs/pcsa_persona_history_final197/gpt4o/pcsa_phase2}"

if (( SHARD_COUNT < 1 )); then
  echo "At least one Qwen endpoint is required." >&2
  exit 1
fi

pids=()
labels=()
for ((shard_index=0; shard_index<SHARD_COUNT; shard_index++)); do
  base_size=$((TOTAL_CASES / SHARD_COUNT))
  remainder=$((TOTAL_CASES % SHARD_COUNT))
  if (( shard_index < remainder )); then
    shard_size=$((base_size + 1))
    shard_start=$((shard_index * shard_size))
  else
    shard_size=$base_size
    shard_start=$((remainder * (base_size + 1) + (shard_index - remainder) * base_size))
  fi
  shard_stop=$((shard_start + shard_size))
  endpoint="${QWEN_ENDPOINTS[$shard_index]}"
  output_dir="$OUTPUT_ROOT/shard-$shard_index"

  echo "Starting shard $shard_index [$shard_start,$shard_stop) via $endpoint"
  QWEN_ENDPOINT="$endpoint" \
  OUTPUT_DIR="$output_dir" \
  BATCH_CASE_CONCURRENCY="${BATCH_CASE_CONCURRENCY:-$shard_size}" \
    "$SCRIPT_DIR/run_pcsa_persona_history_gpt4o_final197.sh" \
      --start "$shard_start" --stop "$shard_stop" "$@" &
  pids+=("$!")
  labels+=("shard-$shard_index")
done

exit_status=0
for index in "${!pids[@]}"; do
  if wait "${pids[$index]}"; then
    echo "${labels[$index]} complete"
  else
    echo "${labels[$index]} failed; rerun this command to resume checkpoints" >&2
    exit_status=1
  fi
done
exit "$exit_status"

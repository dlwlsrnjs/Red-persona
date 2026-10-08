#!/usr/bin/env bash
set -euo pipefail

MODEL_ID="huihui-ai/Llama-3.3-70B-Instruct-abliterated"
MODEL_REVISION="fa13334669544bab573e0e5313cad629a9c02e2c"
SNAPSHOT_PATH="${PERSONA_SNAPSHOT_PATH:-/home/jinkwon/.cache/huggingface/hub/models--huihui-ai--Llama-3.3-70B-Instruct-abliterated/snapshots/${MODEL_REVISION}}"

export CUDA_VISIBLE_DEVICES="${PERSONA_GPU_IDS:-0,1}"

exec python experiments/local_chat_server.py \
  --model-id "${MODEL_ID}" \
  --revision "${MODEL_REVISION}" \
  --snapshot-path "${SNAPSHOT_PATH}" \
  --port "${PERSONA_PORT:-8020}" \
  --device-map balanced \
  --max-output-tokens 3200

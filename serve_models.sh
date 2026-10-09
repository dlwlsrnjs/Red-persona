#!/usr/bin/env bash
# Serve the two local models the RED-Persona pipeline calls over OpenAI-compatible
# HTTP: Qwen2.5-7B-Instruct (researcher/validator) on :8000 and
# Llama-3.1-8B-Lexi-Uncensored-V2 (history generator) on :8002.
#
# Dedicated venv:  .venv (or $RED_PERSONA_VENV / $REDPERSONA_VENV)
# Weights cache :  /data1/users/ljk98/hf_cache   (Qwen + Lexi already present)
#
# Usage:
#   bash serve_models.sh qwen     # start Qwen on GPU 0, port 8000
#   bash serve_models.sh lexi     # start Lexi on GPU 1, port 8002
#   bash serve_models.sh both     # start both (background, logs under ./serve_logs)
#   bash serve_models.sh status   # probe both /v1/models endpoints
#   bash serve_models.sh stop     # stop servers started by this script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${RED_PERSONA_VENV:-${REDPERSONA_VENV:-$SCRIPT_DIR/.venv}}"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Python environment not found: $VENV" >&2
  exit 1
fi
export HF_HOME="${HF_HOME:-/data1/users/ljk98/hf_cache}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}" # weights are cached; never hit the network
# flashinfer JIT-compiles its sampler with ninja+nvcc. Those live inside the venv
# (bin/ninja, site-packages/nvidia/cu13/bin/nvcc) but are not on a bare nohup PATH,
# which crashes EngineCore with FileNotFoundError: 'ninja'. Put them on PATH, point
# CUDA_HOME at the pip CUDA, and fall back to vLLM's native top-k/top-p sampler so
# serving never depends on a runtime compile.
_SITE_PACKAGES="$("$VENV/bin/python" -c 'import site; print(site.getsitepackages()[0])')"
_CUDA_HOME="${REDPERSONA_CUDA_HOME:-$_SITE_PACKAGES/nvidia/cu13}"
export PATH="$VENV/bin:$_CUDA_HOME/bin:$PATH"
export CUDA_HOME="${CUDA_HOME:-$_CUDA_HOME}"
export VLLM_USE_FLASHINFER_SAMPLER=0
PY="$VENV/bin/python"
QWEN_ID="Qwen/Qwen2.5-7B-Instruct"
QWEN_REV="a09a35458c702b33eeacc393d103063234e8bc28"
LEXI_ID="Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2"
LEXI_REV="f4617caeabd21f1820ac89bd125c80eda70901a7"
LOGDIR="$SCRIPT_DIR/serve_logs"
mkdir -p "$LOGDIR"

# --enforce-eager skips vLLM's torch.compile + cudagraph capture, which under the
# 0.28 defaults (combo-kernel benchmarking, flashinfer autotune) takes many minutes
# per model. Eager startup is ~30s and plenty fast for a 7B/8B on an H100.
serve_qwen() {
  CUDA_VISIBLE_DEVICES="${QWEN_SERVE_GPU:-0}" "$PY" -m vllm.entrypoints.openai.api_server \
    --model "$QWEN_ID" --revision "$QWEN_REV" --served-model-name "$QWEN_ID" \
    --host 127.0.0.1 --port 8000 --enforce-eager \
    --gpu-memory-utilization 0.90 --max-model-len 16384 --dtype bfloat16
}
serve_lexi() {
  CUDA_VISIBLE_DEVICES="${LEXI_SERVE_GPU:-1}" "$PY" -m vllm.entrypoints.openai.api_server \
    --model "$LEXI_ID" --revision "$LEXI_REV" --served-model-name "$LEXI_ID" \
    --host 127.0.0.1 --port 8002 --enforce-eager \
    --gpu-memory-utilization 0.90 --max-model-len 16384 --dtype bfloat16
}

status() {
  for p in 8000 8002; do
    echo -n "port $p: "
    curl -s -m 5 "http://127.0.0.1:$p/v1/models" \
      | "$PY" -c 'import sys,json;d=json.load(sys.stdin);print([m["id"] for m in d.get("data",[])])' 2>/dev/null \
      || echo "not responding"
  done
}

case "${1:-}" in
  qwen) serve_qwen ;;
  lexi) serve_lexi ;;
  both)
    nohup bash "$0" qwen >"$LOGDIR/qwen.log" 2>&1 &
    echo "qwen serving -> $LOGDIR/qwen.log (pid $!)"
    nohup bash "$0" lexi >"$LOGDIR/lexi.log" 2>&1 &
    echo "lexi serving -> $LOGDIR/lexi.log (pid $!)"
    echo "wait ~60-120s for weights to load, then: bash serve_models.sh status" ;;
  status) status ;;
  stop)
    pkill -f "vllm.entrypoints.openai.api_server.*$QWEN_ID" 2>/dev/null || true
    pkill -f "vllm.entrypoints.openai.api_server.*$LEXI_ID" 2>/dev/null || true
    echo "stop signal sent" ;;
  *) echo "usage: bash serve_models.sh {qwen|lexi|both|status|stop}"; exit 2 ;;
esac

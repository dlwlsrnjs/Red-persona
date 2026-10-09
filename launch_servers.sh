#!/usr/bin/env bash
# Minimal, dependency-free launcher (no set -e) for the two vLLM servers.
VENV=/data1/users/ljk98/envs/redpersona-vllm
CUDA_H="$VENV/lib/python3.10/site-packages/nvidia/cu13"
export HF_HOME=/data1/users/ljk98/hf_cache
export HF_HUB_OFFLINE=1
export PATH="$VENV/bin:$CUDA_H/bin:$PATH"
export CUDA_HOME="$CUDA_H"
export VLLM_USE_FLASHINFER_SAMPLER=0
cd "$(dirname "$0")"
mkdir -p serve_logs

echo "ninja=$(command -v ninja) nvcc=$(command -v nvcc) flashinfer_sampler=$VLLM_USE_FLASHINFER_SAMPLER"

CUDA_VISIBLE_DEVICES=0 nohup "$VENV/bin/python" -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct --revision a09a35458c702b33eeacc393d103063234e8bc28 \
  --served-model-name Qwen/Qwen2.5-7B-Instruct --host 127.0.0.1 --port 8000 --enforce-eager \
  --gpu-memory-utilization 0.90 --max-model-len 16384 --dtype bfloat16 > serve_logs/qwen.log 2>&1 &
echo "qwen pid $!"

CUDA_VISIBLE_DEVICES=1 nohup "$VENV/bin/python" -m vllm.entrypoints.openai.api_server \
  --model Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
  --served-model-name Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 --host 127.0.0.1 --port 8002 --enforce-eager \
  --gpu-memory-utilization 0.90 --max-model-len 16384 --dtype bfloat16 > serve_logs/lexi.log 2>&1 &
echo "lexi pid $!"
echo "launched"

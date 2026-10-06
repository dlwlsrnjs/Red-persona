"""Persistent local OpenAI-compatible server for a Hugging Face causal LM (CPU).

Loads the model ONCE (e.g. Psychotherapy-LLM/PsyCoPref-Llama3-8B) and serves
POST /v1/chat/completions, so the existing ``adapters/openai_target.py`` can use
it as a target via ``--base-url http://127.0.0.1:<port>/v1`` — no per-call model
reload, no external API key. generate() is serialized with a lock (CPU-bound).

Config via env:
  PCSA_LOCAL_MODEL    model id/path (default Psychotherapy-LLM/PsyCoPref-Llama3-8B)
  PCSA_LOCAL_PORT     port (default 8008)
  PCSA_LOCAL_THREADS  torch CPU threads (default: os.cpu_count())
  PCSA_LOCAL_DTYPE    float32 (default) | bfloat16 | float16
  HF_API_KEY/HF_TOKEN optional, for gated model downloads

Stdlib HTTP only; transformers+torch for the model.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = os.environ.get("PCSA_LOCAL_MODEL", "Psychotherapy-LLM/PsyCoPref-Llama3-8B")
PORT = int(os.environ.get("PCSA_LOCAL_PORT", "8008"))
THREADS = int(os.environ.get("PCSA_LOCAL_THREADS", str(os.cpu_count() or 8)))

# Device: GPU when available (default), else CPU. On GPU default to bfloat16.
_cuda = torch.cuda.is_available()
DEVICE = os.environ.get("PCSA_LOCAL_DEVICE") or ("cuda" if _cuda else "cpu")
_default_dtype = "bfloat16" if DEVICE.startswith("cuda") else "float32"
DTYPE = {"float32": torch.float32, "bfloat16": torch.bfloat16, "float16": torch.float16}[
    os.environ.get("PCSA_LOCAL_DTYPE", _default_dtype)]

_token = os.environ.get("HF_API_KEY") or os.environ.get("HF_TOKEN")
if DEVICE == "cpu":
    torch.set_num_threads(THREADS)

print(f"[local_server] loading {MODEL_ID} device={DEVICE} dtype={DTYPE} ...", flush=True)
_t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL_ID, token=_token)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=DTYPE, token=_token).eval()
model.to(DEVICE)
# Allow concurrent generation up to a limit (per-call KV cache is independent), so the
# GPU is not serialized by a single lock. Set PCSA_LOCAL_CONCURRENCY=1 to force serial.
_gen_sem = threading.Semaphore(int(os.environ.get("PCSA_LOCAL_CONCURRENCY", "4")))
print(f"[local_server] loaded in {time.time()-_t0:.1f}s on {DEVICE}; serving on :{PORT}", flush=True)


def _generate(messages, max_tokens, temperature):
    enc = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt",
                                  return_dict=True)
    enc = {k: v.to(model.device) for k, v in enc.items()}
    prompt_len = enc["input_ids"].shape[-1]
    gen_kwargs = {"max_new_tokens": max_tokens, "pad_token_id": tok.eos_token_id}
    if temperature > 0:
        gen_kwargs.update(do_sample=True, temperature=temperature)
    else:
        gen_kwargs.update(do_sample=False)
    with _gen_sem, torch.no_grad():
        out = model.generate(**enc, **gen_kwargs)
    text = tok.decode(out[0][prompt_len:], skip_special_tokens=True).strip()
    return text, int(prompt_len), int(out.shape[-1] - prompt_len)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client (e.g. timed-out attacker) disconnected; never let it crash the worker

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self):
        if self.path.rstrip("/") == "/v1/models":
            self._send(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            messages = body.get("messages", [])
            if not messages:
                return self._send(400, {"error": {"message": "messages required"}})
            max_tokens = int(body.get("max_tokens", 512))
            temperature = float(body.get("temperature", 0.7))
            text, pt, ct = _generate(messages, max_tokens, temperature)
            self._send(200, {"id": "local-" + str(int(time.time() * 1000)), "object": "chat.completion",
                             "model": MODEL_ID,
                             "choices": [{"index": 0, "finish_reason": "stop",
                                          "message": {"role": "assistant", "content": text}}],
                             "usage": {"prompt_tokens": pt, "completion_tokens": ct,
                                       "total_tokens": pt + ct}})
        except Exception as exc:  # return an OpenAI-shaped error
            import traceback
            traceback.print_exc()
            self._send(500, {"error": {"message": f"{type(exc).__name__}: {exc}"}})


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

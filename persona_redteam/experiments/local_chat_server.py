"""Minimal loopback OpenAI-compatible server for a pinned local chat model.

Supports a single GPU or Accelerate device-map sharding. It intentionally exposes
only /v1/models and /v1/chat/completions and never accepts an external host binding.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-id", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--snapshot-path", type=Path, required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--device-map", choices=("single", "balanced"), default="single")
    ap.add_argument("--max-output-tokens", type=int, default=3200)
    args = ap.parse_args()
    if args.snapshot_path.name != args.revision or not args.snapshot_path.is_dir():
        ap.error("snapshot path must exist and end with the pinned revision")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print("Loading", args.model_id, args.revision, "device_map=", args.device_map, flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.snapshot_path, local_files_only=True)
    if args.device_map == "balanced":
        model = AutoModelForCausalLM.from_pretrained(
            args.snapshot_path, local_files_only=True, torch_dtype=torch.bfloat16,
            device_map="balanced", max_memory={0: "77GiB", 1: "77GiB", "cpu": "160GiB"},
            low_cpu_mem_usage=True,
        ).eval()
    else:
        model = AutoModelForCausalLM.from_pretrained(
            args.snapshot_path, local_files_only=True, torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        ).eval().to("cuda:0")
    input_device = next(model.parameters()).device
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            return

        def send_json(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path.rstrip("/") == "/v1/models":
                self.send_json(200, {"data": [{"id": args.model_id, "revision": args.revision}]})
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/v1/chat/completions":
                return self.send_json(404, {"error": "not found"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                if body.get("model") != args.model_id:
                    return self.send_json(400, {"error": "model identity mismatch"})
                maximum = int(body.get("max_tokens", 900))
                if not 1 <= maximum <= args.max_output_tokens:
                    return self.send_json(400, {"error": "invalid output limit"})
                temperature = float(body.get("temperature", 0))
                with lock, torch.inference_mode():
                    encoded = tokenizer.apply_chat_template(body["messages"], add_generation_prompt=True,
                                                            return_tensors="pt", return_dict=True)
                    encoded = {k: v.to(input_device) for k, v in encoded.items()}
                    start = encoded["input_ids"].shape[-1]
                    options = {"max_new_tokens": maximum, "pad_token_id": tokenizer.eos_token_id,
                               "do_sample": temperature > 0}
                    if temperature > 0:
                        options["temperature"] = temperature
                    output = model.generate(**encoded, **options)
                    tail = output[0][start:]
                    text = tokenizer.decode(tail, skip_special_tokens=True).strip()
                    finish = "length" if len(tail) >= maximum else "stop"
                if not text:
                    return self.send_json(500, {"error": "empty generation"})
                self.send_json(200, {"id": "local-" + str(time.time_ns()), "model": args.model_id,
                                     "revision": args.revision,
                                     "choices": [{"message": {"role": "assistant", "content": text},
                                                  "finish_reason": finish, "index": 0}],
                                     "usage": {"prompt_tokens": int(start), "completion_tokens": len(tail),
                                               "total_tokens": int(start) + len(tail)}})
            except Exception as exc:
                self.send_json(500, {"error": type(exc).__name__ + ": " + str(exc)[:300]})

    ThreadingHTTPServer.daemon_threads = True
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("READY", args.model_id, "port", args.port, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

"""Verify a staged local Ollama with text, image and actual VRAM evidence."""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
from pathlib import Path

from market_rates.common import save
from market_rates.ollama_adapter import request_json, runtime_status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--model", default="qwen3.5:4b")
    args = parser.parse_args()
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    binary = Path(args.binary).resolve(strict=True)
    png = Path(args.image).resolve(strict=True).read_bytes()
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Expected original PNG evidence")
    config = {"models": {"base_url": f"http://127.0.0.1:{args.port}"}}
    # Do not attach to, or accidentally terminate, another server on this port.
    import socket
    with socket.socket() as port_check:
        port_check.bind(("127.0.0.1", args.port))
    env = os.environ.copy()
    env.update(OLLAMA_HOST=f"127.0.0.1:{args.port}", OLLAMA_NO_CLOUD="1",
               OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1")
    status = {"binary": str(binary), "model_directory": env.get("OLLAMA_MODELS"),
              "model": args.model, "port": args.port, "requests": {}}
    with (root / "server.log").open("wb") as log:
        process = subprocess.Popen([str(binary), "serve"], cwd=binary.parent, env=env,
                                   stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        status["pid"] = process.pid
        try:
            for _ in range(30):
                if process.poll() is not None:
                    raise RuntimeError("Staged Ollama exited; inspect server.log")
                try:
                    status["version"] = request_json(config, "/api/version", timeout=2)
                    break
                except RuntimeError:
                    time.sleep(1)
            else:
                raise RuntimeError("Staged Ollama did not become ready")
            for lane in ("text", "vision"):
                content = 'Return exactly this JSON object: {"ok": true}' if lane == "text" else (
                    'Read the Personal customer rate and its term from the attached bank table. '
                    'Return only JSON with personal_rate_pct as a decimal string in percent units, '
                    'and months as an integer. Do not select the Priority or Private customer rates.')
                schema = {"type": "object", "properties": {"ok": {"type": "boolean"}},
                          "required": ["ok"], "additionalProperties": False} if lane == "text" else {
                    "type": "object", "properties": {"personal_rate_pct": {"type": "string"}, "months": {"type": "integer"}},
                    "required": ["personal_rate_pct", "months"], "additionalProperties": False}
                message = {"role": "user", "content": content}
                if lane == "vision":
                    message["images"] = [base64.b64encode(png).decode()]
                payload = {"model": args.model, "stream": False, "think": False,
                           "messages": [message], "format": schema, "keep_alive": "5m",
                           "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 128}}
                print(f"Testing {lane} on staged Ollama...", flush=True)
                started = time.monotonic()
                raw = request_json(config, "/api/chat", payload, timeout=180)
                save(root / f"{lane}-raw.json", raw)
                record = {"elapsed_seconds": round(time.monotonic() - started, 2),
                          "content": raw.get("message", {}).get("content"),
                          "done": raw.get("done"), "done_reason": raw.get("done_reason"),
                          "input_tokens": raw.get("prompt_eval_count"), "output_tokens": raw.get("eval_count"),
                          "runtime": runtime_status(config)}
                status["requests"][lane] = record
                save(root / "result.json", status)
                print(json.dumps({"lane": lane, **record}, ensure_ascii=False), flush=True)
                if raw.get("done") is not True or raw.get("done_reason") != "stop":
                    raise RuntimeError("Model response did not complete")
                json.loads(record["content"])
                if not any(r["gpu_in_use"] for r in record["runtime"]):
                    raise RuntimeError("Model still runs on CPU; do not promote staged runtime")
        except Exception as exc:
            status["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            save(root / "result.json", status)
            try:
                request_json(config, "/api/generate", {"model": args.model, "keep_alive": 0}, timeout=20)
            except RuntimeError:
                pass
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()

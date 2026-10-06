"""Small local-only response-format probe; never a rate-extraction approval."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from market_rates.common import load, save
from market_rates.ollama_adapter import check_model, request_json, runtime_status, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/project.local.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=False)
    config = load(args.config)
    chosen = settings(config)
    check_model(config, chosen["text_model"])
    for name in ("plain", "schema"):
        payload = {"model": chosen["text_model"], "stream": False, "think": False,
                   "messages": [{"role": "user", "content": 'Return exactly this JSON object: {"ok": true}'}],
                   "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 128}, "keep_alive": "5m"}
        if name == "schema":
            payload["format"] = {"type": "object", "properties": {"ok": {"type": "boolean"}},
                                 "required": ["ok"], "additionalProperties": False}
        started = time.monotonic()
        try:
            raw = request_json(config, "/api/chat", payload, timeout=120)
            save(folder / f"{name}-raw.json", raw)
            status = {"content": raw.get("message", {}).get("content"),
                      "done_reason": raw.get("done_reason"),
                      "thinking_present": bool(raw.get("message", {}).get("thinking")),
                      "input_tokens": raw.get("prompt_eval_count"), "output_tokens": raw.get("eval_count")}
        except Exception as exc:
            status = {"error": f"{type(exc).__name__}: {exc}"}
        status["elapsed_seconds"] = round(time.monotonic() - started, 2)
        save(folder / f"{name}-status.json", status)
        print(name, status, flush=True)
    save(folder / "runtime.json", runtime_status(config))


if __name__ == "__main__":
    main()

"""Local-only Ollama chat adapter with vision, schema validation and size guards."""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .common import confined, save, digest
from .schema import normalize
from .extraction_prompt import INSTRUCTIONS
from .extraction_contract import response_schema, contract_instructions


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("本地模型服务不允许跳转到其他地址")


def settings(config):
    options = config.get("models", {})
    base = os.environ.get("RATE_OLLAMA_URL", options.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
    url = urllib.parse.urlparse(base)
    if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username or url.password or url.path or url.query or url.fragment):
        raise ValueError("本地模式只接受本机HTTP地址，例如http://127.0.0.1:11434")
    value = {"base_url": base,
             "text_model": os.environ.get("RATE_TEXT_MODEL", options.get("text_model", "qwen3.5:4b")),
             "vision_model": os.environ.get("RATE_VISION_MODEL", options.get("vision_model", "qwen3.5:4b")),
             "num_ctx": options.get("num_ctx", 16384), "num_predict": options.get("num_predict", 4096),
             "timeout_seconds": options.get("timeout_seconds", 600),
             "max_text_chars": options.get("max_text_chars", 6000),
             "max_images": options.get("max_images", 2),
             "image_token_estimate": options.get("image_token_estimate", 2048),
             "keep_alive": options.get("keep_alive", "5m"), "think": options.get("think", False)}
    for name in ("text_model", "vision_model"):
        model = value[name]
        if not isinstance(model, str) or not model.strip() or "cloud" in model.lower():
            raise ValueError("必须选择已下载的本地模型，不能使用cloud型号")
    for name in ("num_ctx", "num_predict", "timeout_seconds", "max_text_chars", "max_images", "image_token_estimate"):
        if type(value[name]) is not int or value[name] <= 0:
            raise ValueError(f"models.{name}必须为正整数")
    if value["num_ctx"] <= value["num_predict"]:
        raise ValueError("上下文必须大于预留输出长度")
    if type(value["think"]) is not bool:
        raise ValueError("models.think必须为布尔值")
    return value


def request_json(config, endpoint, payload=None, timeout=10):
    base = settings(config)["base_url"]
    request = urllib.request.Request(base + endpoint,
                                     data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={"Content-Type": "application/json"})
    # A system HTTP proxy must not receive local evidence; redirects are disallowed.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    attempts=3 if endpoint=='/api/chat' else 1
    for attempt in range(attempts):
        try:
            with opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in {500,502,503,504} and attempt+1<attempts:
                print(f'本地模型暂时返回HTTP {exc.code}，重试 {attempt+1}/{attempts-1}',flush=True)
                time.sleep(2*(attempt+1));continue
            detail=exc.read().decode('utf8',errors='replace')[:600]
            raise RuntimeError(f"本地Ollama返回HTTP {exc.code}：{detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise RuntimeError("无法连接本地Ollama或运行超时；请启动Ollama并检查模型、显存和超时配置") from exc


def check_model(config, model, vision=False):
    info = request_json(config, "/api/show", {"model": model}, timeout=10)
    if info.get("remote_host") or info.get("remote_model"):
        raise ValueError("模型指向云端；本项目本地模式拒绝发送证据")
    capabilities = info.get("capabilities", [])
    if "completion" not in capabilities:
        raise ValueError(f"{model}不支持文本生成，或Ollama版本过旧无法确认模型能力")
    if vision and "vision" not in capabilities:
        raise ValueError(f"{model}没有图片输入能力，不能用作VLM")
    return {"name": model, "capabilities": capabilities, "details": info.get("details", {})}


def preflight(config):
    chosen = settings(config)
    models = []
    for name in dict.fromkeys((chosen["text_model"], chosen["vision_model"])):
        models.append(check_model(config, name, vision=name == chosen["vision_model"]))
    return {"provider": "ollama", "base_url": chosen["base_url"], "models": models,
            "same_model_two_modalities": chosen["text_model"] == chosen["vision_model"],
            "parallel_requests": 1}


def runtime_status(config):
    """Read actual loaded-model placement; model capability alone is not GPU proof."""
    rows = request_json(config, "/api/ps").get("models", [])
    return [{"name": r.get("name", r.get("model")), "size_bytes": r.get("size"),
             "vram_bytes": r.get("size_vram"), "context_length": r.get("context_length"),
             "gpu_in_use": r.get("size_vram", 0) > 0} for r in rows]


def validate_extraction(result):
    expected = {"offers", "inventory", "coverage_complete", "unreadable"}
    if not isinstance(result, dict) or set(result) != expected:
        raise ValueError("模型输出不符合提取结构，不能当作已完成")
    if type(result["coverage_complete"]) is not bool:
        raise ValueError("coverage_complete必须为布尔值")
    for name in ("offers", "inventory", "unreadable"):
        if not isinstance(result[name], list):
            raise ValueError(f"{name}必须为列表")
    if not all(isinstance(s, str) for s in result["unreadable"]):
        raise ValueError("unreadable必须为文本列表")
    result["offers"] = [normalize(r) for r in result["offers"]]
    seen = set()
    for item in result["inventory"]:
        if (not isinstance(item, dict) or set(item) != {"page_id", "row_count", "notes"}
                or not isinstance(item["page_id"], str) or not item["page_id"]
                or type(item["row_count"]) is not int or item["row_count"] < 0
                or not isinstance(item["notes"], str) or item["page_id"] in seen):
            raise ValueError("逐页清单格式错误、重复或行数不合法")
        seen.add(item["page_id"])
    return result


def build_payload(lane, pages, evidence_dir, config, as_of):
    if lane not in {"llm", "vlm"}:
        raise ValueError("无效提取路线")
    chosen = settings(config)
    if not pages:
        raise ValueError("没有证据页，不能运行模型")
    if lane == "llm" and sum(len(p["text"]) for p in pages) > chosen["max_text_chars"]:
        raise ValueError("本地文字批次超限；请缩小到产品表格及完整关联条款，不会静默截断")
    count = sum(len(p.get("images", [])) for p in pages) if lane == "vlm" else 0
    if count > chosen["max_images"]:
        raise ValueError("本地截图批次超限；请先配置银行页面范围或扩大经实测可承受的批次，不能丢弃截图")
    banks = {p["bank"] for p in pages}
    catalog = [{k: v for k, v in p.items() if k in ("id", "bank", "name")}
               for p in config.get("products", []) if p["bank"] in banks]
    header = json.dumps({"as_of": as_of, "scope": "SGD promo", "catalog": catalog}, ensure_ascii=False)
    schema = response_schema(pages)
    manifest = [{"page_id": p["id"], "bank": p["bank"], "image_files": p.get("images", [])} for p in pages]
    messages = [{"role": "system", "content": INSTRUCTIONS + contract_instructions(pages) + "\nJSON schema:\n" + json.dumps(schema)},
                {"role": "user", "content": header}]
    messages.append({"role": "user", "content": "Evidence document manifest (IDs are fixed): " + json.dumps(manifest)})
    for page in pages:
        descriptor = f'page_id={page["id"]}; bank={page["bank"]}; url={page["url"]}'
        message = {"role": "user", "content": descriptor}
        if lane == "llm":
            message["content"] += "\n原始网页文字:\n" + page["text"]
        else:
            if not page.get("images"):
                raise ValueError("VLM缺少截图，禁止以文字代替视觉验证")
            message["content"] += "\n图片顺序及文件名：" + json.dumps(page["images"], ensure_ascii=False)
            message["content"] += "\n证据locator必须写对应文件名及表头/行位置。"
            message["images"] = []
            for name in page["images"]:
                data = confined(evidence_dir, name).read_bytes()
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("本地视觉证据必须是采集器保存的PNG截图；SVG演示不是实际截图")
                message["images"].append(base64.b64encode(data).decode())
        messages.append(message)
    # Text bytes conservatively bound ordinary text tokens. Image token estimates
    # are model-dependent; pilot measurements are still required.
    budget = sum(len(m["content"].encode("utf8")) for m in messages) + count * chosen["image_token_estimate"] + 1024
    if budget + chosen["num_predict"] > chosen["num_ctx"]:
        raise ValueError("本批证据可能超出本地上下文预算；请缩小完整证据范围或验证更大的num_ctx，不会截断后继续")
    return {"model": chosen["text_model"] if lane == "llm" else chosen["vision_model"],
            "stream": False, "messages": messages, "format": schema,
            "think": chosen["think"], "keep_alive": chosen["keep_alive"],
            "options": {"temperature": 0, "num_ctx": chosen["num_ctx"], "num_predict": chosen["num_predict"]}}


def extract(lane, pages, evidence_dir, config, as_of):
    if pages and {p["bank"] for p in pages} == {"SCB"}:
        from .scb_extractor import extract as extract_scb
        return extract_scb(lane, pages, evidence_dir, config, as_of)
    if config.get('extraction_profile') == 'multi-bank-literal-v1':
        from .multi_bank_extractor import extract as extract_units
        return extract_units(lane, pages, evidence_dir, config, as_of)
    payload = build_payload(lane, pages, evidence_dir, config, as_of)
    check_model(config, payload["model"], vision=lane == "vlm")
    chosen = settings(config)
    raw = request_json(config, "/api/chat", payload, timeout=chosen["timeout_seconds"])
    # Keep the exact server response even if JSON/content validation later fails.
    # Model inputs (images) and credentials are not included in this response log.
    response_path = Path(evidence_dir).resolve().parent / ("ollama-" + lane + "-response-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".json")
    save(response_path, raw)
    if raw.get("done") is not True or raw.get("done_reason") != "stop":
        raise RuntimeError("本地模型未正常完成或输出被截断；不能使用部分结果")
    if raw.get("prompt_eval_count", 0) + raw.get("eval_count", 0) >= chosen["num_ctx"]:
        raise RuntimeError("本次模型已达到上下文预算，需缩小证据范围后重新提取")
    try:
        content = raw.get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("服务返回空content；原始响应已保留，不能当作成功提取")
        result = validate_extraction(json.loads(content))
    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        raise ValueError(f"本地模型输出校验失败: {exc}") from exc
    page_ids = {p["id"] for p in pages}
    if any(i["page_id"] not in page_ids for i in result["inventory"]):
        raise ValueError("模型清单包含未提供的证据页")
    if any(e["page_id"] not in page_ids for r in result["offers"] for e in r["evidence"]):
        raise ValueError("报价引用包含未提供的证据页")
    return result, {"provider": "ollama", "model": raw.get("model", payload["model"]),
                    "extraction_contract": "standard-v2",
                    "request_sha256": digest(payload),
                    "schema_sha256": digest(payload["format"]),
                    "requested_model": payload["model"], "lane": lane,
                    "same_model_two_modalities": chosen["text_model"] == chosen["vision_model"],
                    "usage": {"input_tokens": raw.get("prompt_eval_count"), "output_tokens": raw.get("eval_count")},
                    "total_duration_ns": raw.get("total_duration"),
                    "raw_response_file": response_path.name,
                    "context_window": chosen["num_ctx"], "cloud_fallback": False}

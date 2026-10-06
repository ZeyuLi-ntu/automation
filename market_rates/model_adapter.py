"""Local-only model dispatch. Cloud model execution is disabled for this project."""
from __future__ import annotations

def provider(config):
    value = config.get("models", {}).get("provider", "ollama")
    if value != "ollama":
        raise ValueError("本项目只允许本地Ollama；云端模型入口已禁用，请设置models.provider=ollama")
    return value


def workers(config):
    # Independent inputs do not require concurrent execution on an 8GB GPU.
    provider(config)
    return 1


def preflight(config):
    provider(config)
    from .ollama_adapter import preflight as check
    return check(config)


def extract(lane, pages, evidence_dir, config, as_of):
    if lane not in {"llm", "vlm"}:
        raise ValueError("无效提取路线")
    provider(config)
    from .ollama_adapter import extract as run
    return run(lane, pages, evidence_dir, config, as_of)

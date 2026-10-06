"""Disabled legacy entry point; retained only to fail clearly for old callers."""


def extract(lane, pages, evidence_dir, config, as_of):
    raise ValueError("云端模型入口已禁用。本项目只使用本机Ollama，不读取GPT密钥或发送API请求。")

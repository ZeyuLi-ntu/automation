from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import hashlib
import html
import uuid
from .capture import capture_sources
from .common import load, save, digest, confined
from .model_adapter import extract, preflight, workers
from .verify import assess
from .review import write_review
from .workbook_policy import bank_in_scope


def configuration(path):
    config = load(path)
    if isinstance(config.get("sources"), str):
        config["sources"] = load(Path(path).parent / config["sources"])
    for key in ('sources', 'products'):
        if key in config:
            config[key] = [row for row in config[key] if bank_in_scope(row['bank'])]
    if 'expected_banks' in config:
        config['expected_banks'] = [bank for bank in config['expected_banks'] if bank_in_scope(bank)]
    return config


def live_run(config, out, as_of, store):
    date.fromisoformat(as_of)
    if as_of != datetime.now(timezone(timedelta(hours=8))).date().isoformat():
        raise ValueError("实时网页只能作为本次采集日证据；历史日期须使用当时的存档，不能用今日网页回填")
    if not config.get("expected_banks") or not config.get("products"):
        raise ValueError("请先配置预期银行及产品目录，不能把零覆盖当作成功")
    out = Path(out)
    if out.exists():
        raise ValueError("运行目录已存在，请为新采集指定新目录，防止混合证据")
    model_status = preflight(config)
    out.mkdir(parents=True)
    pages, errors = capture_sources(config, out / "evidence")
    lanes = {lane: {"offers": [], "coverage_complete": True, "unreadable": [], "inventory": []} for lane in ("llm", "vlm")}
    metadata = []
    banks = sorted({p["bank"] for p in pages})
    for bank in banks:
        packet = [p for p in pages if p["bank"] == bank]
        # Local requests run sequentially to fit memory, but never share answers.
        with ThreadPoolExecutor(max_workers=workers(config)) as pool:
            futures = {lane: pool.submit(extract, lane, packet, out / "evidence", config, as_of) for lane in lanes}
            for lane, future in futures.items():
                try:
                    result, meta = future.result()
                    save(out / f"model-{digest(bank)[:12]}-{lane}.json", {"result": result, "metadata": meta})
                    metadata.append({"bank": bank, "lane": lane, **meta})
                    errors.extend(item for item in meta.get("review_required", []) if item not in errors)
                    lanes[lane]["offers"].extend(result["offers"])
                    lanes[lane]["inventory"].extend(result["inventory"])
                    lanes[lane]["unreadable"].extend(result["unreadable"])
                    lanes[lane]["coverage_complete"] &= result["coverage_complete"]
                except Exception as exc:
                    errors.append(f"{bank} {lane}提取失败: {type(exc).__name__}: {str(exc)[:250]}")
                    lanes[lane]["coverage_complete"] = False
    if not pages:
        for result in lanes.values():
            result["coverage_complete"] = False
    run = {"id": uuid.uuid4().hex, "as_of": as_of, "demo": False,
           "created_at": datetime.now(timezone.utc).isoformat(), "pages": pages, "errors": errors,
           "metadata": metadata, "model_status": model_status, "evidence_hash": digest(pages), **lanes}
    save(out / "run.json", run)
    save(out / "config.snapshot.json", config)
    evidence_index(pages, out / "evidence")
    return evaluate(out, store)


def check_evidence(run, folder):
    if digest(run["pages"]) != run["evidence_hash"]:
        raise ValueError("run.json证据摘要不匹配，不能使用已变化证据")
    for p in run["pages"]:
        for name, expected in p.get("image_hashes", {}).items():
            if hashlib.sha256(confined(folder, name).read_bytes()).hexdigest() != expected:
                raise ValueError("截图文件已改变，旧复核结论失效")


def evaluate(out, store):
    out = Path(out)
    run = load(out / "run.json")
    check_evidence(run, out / "evidence")
    result = assess(run, load(out / "config.snapshot.json"), store)
    write_review(result, out)
    return result


def evidence_index(pages, out):
    parts = ['<!doctype html><meta charset="utf-8"><title>采集证据</title><h1>采集证据索引</h1>']
    for p in pages:
        parts += [f'<h2>{html.escape(p["bank"])} / {html.escape(p["id"])}</h2>',
                  f'<p>{html.escape(p["url"])}</p>', f'<a href="{html.escape(p["id"])}.txt">原文</a>']
        for name in p.get("images", []):
            parts.append(f'<p><a href="{html.escape(name)}">{html.escape(name)}</a></p>')
    Path(out, "index.html").write_text(''.join(parts), encoding="utf8")

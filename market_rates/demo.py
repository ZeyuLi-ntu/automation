"""Synthetic fixtures: no network and no claim that a model saw these images."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
from .common import digest, save
from .verify import assess, apply_decisions
from .review import write_review
from .pipeline import evidence_index


def offer(bank="DEMO_A", product="demo-a", audience="personal", rate="1.7"):
    return {"bank": bank, "product_id": product, "product_name": "演示定存（非真实产品）", "currency": "SGD",
            "rate_type": "promo", "tenor_value": 6, "tenor_unit": "M", "audience": audience,
            "channel": "online", "amount_min": "20000", "amount_max": None,
            "min_inclusive": True, "max_inclusive": False, "amount_currency": "SGD", "amount_is_equivalent": False,
            "fresh_funds": "yes", "conditions": "演示：仅用于软件测试", "rate_pct": rate,
            "rate_basis": "annual_nominal", "valid_from": "2026-09-01", "valid_to": "2026-09-30",
            "availability": "available", "evidence": [{"page_id": bank, "quote": f"{audience} {rate}%", "locator": bank + ".svg 演示行"}]}


def fixtures():
    a = offer(); b = offer(audience="premier", rate="1.8")
    c = offer("DEMO_B", "demo-b", rate="1.65")
    d = deepcopy(c); d["rate_pct"] = "1.75"
    config = {"expected_banks": ["DEMO_A", "DEMO_B"], "sources": [], "tenor_map": {},
              "products": [{"id": "demo-a", "bank": "DEMO_A", "name": "演示A", "personal_status": "present"},
                           {"id": "demo-b", "bank": "DEMO_B", "name": "演示B", "personal_status": "present"}]}
    pages = [{"id": bank, "bank": bank, "url": "https://example.invalid/" + bank, "ok": True, "complete": True,
              "text": "演示数据，不是官网报价。personal 1.7% premier 1.8% personal 1.65% personal 1.75%",
              "images": [bank + ".svg"]} for bank in config["expected_banks"]]
    run = {"id": "demo-20260924", "as_of": "2026-09-24", "demo": True, "pages": pages, "errors": [],
           "evidence_hash": digest(pages),
           "llm": {"offers": [a, b, c], "coverage_complete": True, "unreadable": [],
                   "inventory": [{"page_id": p["id"], "row_count": 2, "notes": "手写演示fixture"} for p in pages]},
           "vlm": {"offers": [deepcopy(a), deepcopy(b), d], "coverage_complete": True, "unreadable": [],
                   "inventory": [{"page_id": p["id"], "row_count": 2, "notes": "手写演示fixture，并非真实模型提取"} for p in pages]}}
    return config, run


def make_demo(out, store):
    out = Path(out)
    if out.exists():
        raise ValueError("演示目录已存在，请指定新目录")
    evidence = out / "evidence"
    evidence.mkdir(parents=True)
    config, run = fixtures()
    for page in run["pages"]:
        (evidence / f'{page["id"]}.txt').write_text(page["text"], encoding="utf8")
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="180"><rect width="700" height="180" fill="#eef5ff"/><text x="24" y="45" font-size="22">SYNTHETIC TEST DATA - NOT A WEBSITE SCREENSHOT</text><text x="24" y="95" font-size="20">Personal 1.70% / Premier 1.80%</text><text x="24" y="140" font-size="18">No API calls. Model outputs are handwritten fixtures.</text></svg>'
        file = evidence / page["images"][0]
        file.write_text(svg, encoding="utf8")
        page["image_hashes"] = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()}
    run["evidence_hash"] = digest(run["pages"])
    save(out / "config.snapshot.json", config)
    save(out / "run.json", run)
    evidence_index(run["pages"], evidence)
    result = assess(run, config, store)
    write_review(result, out)
    # Separate demonstration of a resolved workflow, never used on live runs.
    decisions = [{"id": i["id"], "fingerprint": i["fingerprint"], "action": "llm" if i["llm"] else "acknowledge",
                  "author": "演示脚本", "reason": "仅为离线流程展示，非人工核实真实报价", "persist": False}
                 for i in result["issues"]]
    save(out / "demo-decisions.example.json", decisions)
    apply_decisions(run, config, store, decisions)
    resolved = assess(run, config, store)
    write_review(resolved, out / "resolved-example", evidence_href="../evidence/index.html")
    return result, resolved

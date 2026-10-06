"""Compare frozen real SCB extractions with evidence-read reference facts.

The reference is for evaluation only. It is never supplied to either model.
It does not approve model records or publish a market report.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from market_rates.common import load, save
from market_rates.ollama_adapter import runtime_status
from market_rates.pipeline import evaluate
from market_rates.store import Store
from market_rates.clause_review import clause_differences
from market_rates.extraction_contract import check_reference

REFERENCE = {"personal": "1.7", "preferred": "1.8", "private": "2"}
FIELDS = {"bank": "SCB", "product_id": "scb-sgd-fresh-funds", "currency": "SGD", "rate_type": "promo",
          "tenor_value": 6, "tenor_unit": "M", "amount_min": "25000", "amount_max": None,
          "min_inclusive": True, "max_inclusive": False, "amount_currency": "SGD", "amount_is_equivalent": False,
          "channel": "online_banking|sc_mobile", "valid_from": None,
          "fresh_funds": "yes", "rate_basis": "annual_nominal", "valid_to": "2026-09-30", "availability": "available"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--probe", help="Optional folder with separate small-request diagnostic results")
    args = parser.parse_args()
    folder = Path(args.run)
    run = load(folder / "run.json")
    if run["evidence_hash"] != "90e1ef426f731b8b9431cec3aa12bc151a2aee0cf5c399f08cd432741535accf":
        raise ValueError("这份参考答案仅适用于已人工阅读的9月24日SCB证据，其他证据需另建基准")
    # Add an independently observed source conflict to review only after model
    # extraction. Never put reference rates or this conclusion into model inputs.
    finding = "助手证据核对：网页活动起始日2026-08-28，关联条款PDF起始日2026-09-01；需确认适用日期及条款优先级"
    if finding not in run["errors"] and not any("来源日期冲突 valid_from" in error for error in run["errors"]):
        run["errors"].append(finding)
        save(folder / "run.json", run)
    store = Store(folder / "pilot.sqlite3")
    try:
        review = evaluate(folder, store)
    finally:
        store.close()
    report = {"scope": "Single SCB SGD promotion table plus its two-page linked terms PDF",
              "source": run["pilot"], "as_of": run["as_of"], "lanes": {},
              "reference_basis": "Assistant inspection of captured source text and original screenshots; not user approval",
              "source_conflict": {"field": "valid_from", "web": "2026-08-28", "pdf": "2026-09-01",
                                  "requires_review": True},
              "published": False, "pending_review_items": review["pending"],
              "runtime": runtime_status(load(folder / "config.snapshot.json"))}
    report["clause_differences"] = clause_differences(run.get("metadata", []))
    for lane in ("llm", "vlm"):
        result = run[lane]
        checks = []
        for audience, rate in REFERENCE.items():
            candidates = [r for r in result["offers"] if r["audience"] == audience]
            problems = []
            if len(candidates) != 1:
                problems.append(f"预期1条{audience}记录，实际{len(candidates)}条")
            elif candidates:
                expected = {**FIELDS, "rate_pct": rate}
                problems.extend(f'{field}: expected={value!r}, actual={candidates[0].get(field)!r}'
                                for field, value in expected.items() if candidates[0].get(field) != value)
            checks.append({"audience": audience, "reference_rate_pct": rate, "problems": problems,
                           "matched_core_fields": not problems})
        raw_file = folder / f"model-{lane}.json"
        metadata = load(raw_file).get("metadata", {}) if raw_file.exists() else {}
        failures = sorted(folder.glob(f"failure-{lane}-*.json"))
        if not raw_file.exists() and failures:
            failure = load(failures[-1])
            metadata = {"elapsed_seconds": failure["elapsed_seconds"], "error": failure["error"]}
        evidence_problems = []
        pages = {p["id"]: p for p in run["pages"]}
        for row in result["offers"]:
            if not row.get("evidence"):
                evidence_problems.append("报价缺少证据")
            for reference in row.get("evidence", []):
                try:
                    check_reference(reference, pages, lane)
                except ValueError as exc:
                    evidence_problems.append(str(exc))
        clauses = metadata.get("clause_ledger", [])
        clause_numbers = [c["number"] for c in clauses]
        report["lanes"][lane] = {"offer_count": len(result["offers"]), "checks": checks,
                                 "extraction_completed": raw_file.exists(),
                                 "matched_core_rows": sum(c["matched_core_fields"] for c in checks) if raw_file.exists() else None,
                                 "coverage_claim": result["coverage_complete"], "unreadable": result["unreadable"],
                                 "evidence_reference_problems": sorted(set(evidence_problems)),
                                 "all_16_numbered_clauses_present_once": sorted(clause_numbers) == list(range(1, 17)),
                                 "extracted_start_dates": sorted({r["valid_from"] for r in result["offers"] if r["valid_from"]}),
                                 "metadata": metadata}
    report["errors"] = run["errors"]
    if args.probe:
        probe = Path(args.probe)
        report["small_request_probe"] = {name: load(probe / f"{name}-status.json") for name in ("plain", "schema")}
        report["small_request_probe"]["scope"] = "Simple text response only; does not verify vision, full extraction or mandatory schema enforcement"
    save(folder / "benchmark.json", report)
    parts = ['<!doctype html><meta charset="utf-8"><title>渣打本地模型试点</title>',
             '<style>body{font:16px system-ui;margin:30px;max-width:1100px;color:#17324b}td,th{padding:12px;border:1px solid #cbd4dd}table{border-collapse:collapse}pre{white-space:pre-wrap}aside{padding:16px;background:#fff1d8}</style>',
             '<h1>渣打SGD促销：本地模型试点</h1>',
             '<p>来源：利率链接.xlsx → 工作表1 → D67；仅测试该促销及关联PDF，不代表全银行覆盖。</p>',
             '<aside>未发布正式报价。网页起始日为2026-08-28，条款PDF为2026-09-01。即使两路给出相同日期，也需要保留这项来源冲突。</aside>',
             '<p><a href="evidence/index.html">证据索引</a> · <a href="review.html">逐项复核页面</a></p>',
             '<table><tr><th>路线</th><th>记录数</th><th>核心字段匹配</th><th>用时</th><th>条款编号1–16齐全</th><th>证据引用</th></tr>']
    for lane, row in report["lanes"].items():
        seconds = row["metadata"].get("elapsed_seconds")
        elapsed = f'{seconds:.1f}秒' if seconds is not None else '未成功返回'
        matched = f'{row["matched_core_rows"]}/3' if row["extraction_completed"] else '提取未通过，无法评分'
        references = '通过' if row['extraction_completed'] and not row['evidence_reference_problems'] else '未通过'
        clauses = '是' if row['all_16_numbered_clauses_present_once'] else '否'
        parts.append(f'<tr><td>{lane.upper()}</td><td>{row["offer_count"]}</td><td>{matched}</td><td>{elapsed}</td><td>{clauses}</td><td>{references}</td></tr>')
    parts.append('</table><p>核心字段包括利率、金额边界、原始期限、客群、币种、网上银行/SC Mobile渠道、有效期终点，以及冲突起始日留空。条款编号齐全不代表每个字都正确，3条样本也不代表总体准确率。</p>')
    parts.append('<p>文字路线：模型读取网页文字，程序保留PDF原始完整条款。视觉路线：同一本地模型分别读取网页截图和两页PDF图片，转录条款。视觉输入不含文字路线答案；两路使用同一模型，不保证错误相互独立。</p>')
    parts.append(f'<h2>待人工核对的条款差异：{len(report["clause_differences"])}</h2><p>只忽略空白和直弯引号差异；数字、否定词、and/or等连接词保留比较。差异已加入复核阻断，未自动采用任一路。</p>')
    for difference in report["clause_differences"]:
        parts.append(f'<details><summary>条款{difference["number"]}：{html.escape(difference["reason"])}</summary>')
        for lane in ('llm', 'vlm'):
            for clause in difference[lane]:
                parts.append(f'<p><b>{lane.upper()}</b> — {html.escape(clause["locator"])}</p><blockquote>{html.escape(clause["quote"])}</blockquote>')
        parts.append('</details>')
    parts.append(f'<p>当前待复核项共{review["pending"]}项，包括初次报价核验。没有自动批准，没有写入正式Excel。</p>')
    parts.append('<h2>参考报价</h2><p>均为6个月、SGD25,000起存、新资金：Personal 1.70%，Priority Banking 1.80%，Priority Private 2.00%。Personal排序值应为1.70%，全客群最高值应为2.00%。</p>')
    if args.probe:
        parts.append('<h2>独立的小请求诊断</h2><p>普通输出及带JSON约束的简单文字请求结果如下。该检查不能证明视觉能力、完整报价提取或格式约束强制生效。</p><pre>'
                     + html.escape(json.dumps(report["small_request_probe"], ensure_ascii=False, indent=2)) + '</pre>')
    parts.append('<details><summary>原始测评记录</summary><pre>' + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + '</pre></details>')
    (folder / "benchmark.html").write_text(''.join(parts), encoding="utf8")
    print(json.dumps({lane: {"count": r["offer_count"], "core_matches": r["matched_core_rows"], "seconds": r["metadata"].get("elapsed_seconds")}
                      for lane, r in report["lanes"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()

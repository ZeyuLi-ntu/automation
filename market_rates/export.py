"""Generate a concrete write plan; Excel performs native insertions and recalculation."""
from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path
from .common import save
from .xlsx_read import read_xlsx
from .schema import group_key
from .rules import COLORS
from .workbook_policy import workbook_policy,included_groups,daily_change_cells,bank_blocks


def make_plan(result, config, mapping, report_template, rainbow_template, out):
    if result["pending"]:
        raise ValueError("还有未解决复核项，不能生成正式Excel写入计划；可查看HTML草稿")
    report_template, rainbow_template = Path(report_template).resolve(), Path(rainbow_template).resolve()
    expected = hashlib.sha256(report_template.read_bytes()).hexdigest()
    if mapping.get("template_sha256") != expected:
        raise ValueError("模板版本变化，请重新核对单元格映射；不能使用旧行号")
    book = read_xlsx(report_template)
    cells = book["SGD促销"]
    entries = {m["group_id"]: m for m in mapping.get("entries", [])}
    policy=workbook_policy(config)
    groups = included_groups(result["groups"],policy)
    updates = included_groups(result.get("updates", result['groups']),policy)
    highest={}
    ordered=[]
    for tenor in dict.fromkeys(g['display_tenor'] for g in groups):
        blocks=[dict(bank=g['bank'],group=g,rank_rate=str(Decimal(g['main_pct'])/100),prior_index=n) for n,g in enumerate(groups) if g['display_tenor']==tenor]
        ordered.extend(b['group'] for b in bank_blocks(blocks))
    groups=ordered
    for g in groups:
        key=g['bank']+'/'+g['display_tenor']
        best=max(g['details'],key=lambda r:Decimal(r['rate_pct']))
        if key not in highest or Decimal(best['rate_pct'])>Decimal(highest[key]['rate_pct']):highest[key]=best
    standard = {"1M", "3M", "6M", "9M", "12M", "18M", "24M"}
    if any(g["display_tenor"] not in standard for g in groups):
        raise ValueError("首版Excel彩虹模板尚未配置该独立期限栏；请扩展模板后导出，不能丢弃报价")
    missing = [g["id"] for g in updates if g["id"] not in entries or not entries[g["id"]].get("confirmed")]
    if missing:
        raise ValueError("以下产品尚未确认模板映射: " + ", ".join(missing))
    summary = book["最高报价汇总 "]
    aliases = config.get("template_bank_aliases", {})
    bank_slots = {aliases.get(summary.get(f'B{r}'), summary.get(f'B{r}')) for r in range(4, 24)}
    absent = {g["bank"] for g in groups} - bank_slots
    if absent:
        raise ValueError("这些银行尚无最高汇总模板位置，请先扩展模板: " + ", ".join(sorted(absent)))
    writes, new_rows, used = [], [], set()
    # Inserting a column correctly shifts old formulas, but the weekly delta must
    # be rebound to new-current minus previous, rather than previous minus older.
    delta_formulas = daily_change_cells(read_xlsx(report_template, formulas=True,merge_anchors_only=True)["SGD促销"])
    bank_spans={}
    for g in updates:
        m = entries[g["id"]]
        row = m.get("row") or m.get("insert_before")
        if type(row) is not int or row < 5:
            raise ValueError("映射必须提供有效row或insert_before")
        if bool(m.get("row")) == bool(m.get("insert_before")):
            raise ValueError("已有行和新插入行只能指定一种")
        if cells.get(f'A{row}') != m.get("expected_bank_label"):
            raise ValueError(f"模板第{row}行银行标签与确认映射不一致")
        item = {"original_row": row, "bank": g["bank"], "main_pct": g["main_pct"],
                "group_id": g["id"], "status": g.get("status", "已检查"),
                "condition": g.get("status", "已检查") + "\n" + "\n".join(condition(r) for r in g["details"])}
        if m.get("insert_before"):
            labels=sorted((int(a[1:]),v) for a,v in cells.items() if re.fullmatch(r'A\d+',a) and v)
            anchor=m.get('bank_row')
            if anchor is None:
                anchor=row if cells.get(f'A{row}')==g['bank'] else max((r for r,v in labels if r<row),default=None)
            if anchor is not None and cells.get(f'A{anchor}')==g['bank']:
                end=min((r for r,v in labels if r>anchor),default=max(int(re.search(r'\d+',a)[0]) for a in cells)+1)-1
                if row not in (anchor,end+1):raise ValueError('新增产品必须位于原银行区域边界')
                item['bank_anchor']=anchor
                bank_spans[anchor]=dict(bank=g['bank'],start=anchor,end=end)
            elif any(v==g['bank'] for r,v in labels):
                raise ValueError('已有银行新增产品必须指定同一期限下的 bank_row 并扩展原银行区域')
            new_rows.append(item)
        else:
            if row in used:
                raise ValueError("多个不同产品不能写入同一单元格，请为新产品配置insert_before")
            used.add(row); writes.append(item)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    suffix = "演示" if result["demo"] else "SGD试点"
    plan = {"schema_version": 1, "run_id": result["run_id"], "as_of": result["as_of"], "scope": "SGD promo only",
            "demo": result["demo"], "report_template": str(report_template), "rainbow_template": str(rainbow_template),
            "report_sha256": expected, "rainbow_sha256": hashlib.sha256(rainbow_template.read_bytes()).hexdigest(),
            "report_output": str(out / f'{result["as_of"].replace("-", "")}_{suffix}调研.xlsx'),
            "rainbow_output": str(out / f'{result["as_of"].replace("-", "")}_{suffix}彩虹表.xlsx'),
            "writes": writes, "new_rows": new_rows, "delta_formulas": delta_formulas,
            "groups": groups, "highest": highest, "updates": updates,"bank_spans":list(bank_spans.values()),"workbook_policy":policy,
            "colors": COLORS, "bank_aliases": config.get("template_bank_aliases", {}),
            "scope_note": "本文件仅更新SGD促销。其他币种和挂牌区域保留原期数据，不能视为本期已核查。"}
    save(out / "export-plan.json", plan)
    return out / "export-plan.json"


def condition(r):
    low = ("≥" if r["min_inclusive"] else ">") + (r["amount_min"] or "待核实")
    high = (("≤" if r["max_inclusive"] else "<") + r["amount_max"]) if r["amount_max"] else "无明确上限"
    equivalent = "等值" if r["amount_is_equivalent"] else ""
    rate = r["rate_pct"] + "%" if r["rate_pct"] is not None else "-"
    return (f'{rate} / {r["product_name"]} / 实际{r["tenor_value"]}{r["tenor_unit"]} / '
            f'{r["audience"]} / {equivalent}{r["amount_currency"]} {low}, {high} / {r["channel"]} / '
            f'新资金:{r["fresh_funds"]} / {r["conditions"]} / 有效期:{r["valid_from"] or "未注明"}至{r["valid_to"] or "未注明"}')

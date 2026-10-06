"""Evidence-bounded extraction contracts; never contain benchmark prices or dates."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import re

from .schema import EXTRACTION_SCHEMA

AUDIENCES = {
    "personal": "personal", "personal banking": "personal",
    "priority banking": "preferred",
    "priority private": "private", "priority private banking": "private",
    "all customers": "all",
}


def compact(value):
    return " ".join(value.split())


def response_schema(pages):
    schema = deepcopy(EXTRACTION_SCHEMA)
    ids = [p["id"] for p in pages]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate input evidence IDs")
    page_id = {"type": "string", "enum": ids}
    offer = schema["properties"]["offers"]["items"]
    offer["properties"]["evidence"]["items"]["properties"]["page_id"] = page_id
    schema["properties"]["inventory"]["items"]["properties"]["page_id"] = page_id
    return schema


def contract_instructions(pages):
    instructions = """
Evidence rules:
- page_id is an opaque document ID from the supplied manifest. It is NEVER an image filename.
- One inventory entry per supplied document ID, including documents without rate tables.
  row_count counts quoted deposit offer rows, NOT numbered legal clauses. A terms-only PDF has zero offer rows.
- An entire multi-page PDF has ONE document ID. Read ALL its images. Put image filenames in locator only.
- Evidence quotes must be SHORT, EXACT, CONTIGUOUS source excerpts. Do not translate, paraphrase,
  join distant sentences, or insert ellipses. Use separate evidence entries for separate excerpts.
- For an image quote, locator must name the actual image file and visible section/row/clause.
- Preserve the original tenor unit; never estimate a month as 30 days.
- Read all eligibility: deposit amount, fresh funds, valid accounts, holding to maturity, early withdrawal,
  customer status through maturity, renewal rates, other-offer exclusions and applicable date conflicts.
"""
    return instructions


def parse_tenor(text):
    year=re.fullmatch(r'(\d+)\s*(?:years?|年)',compact(text),flags=re.I)
    if year and int(year[1])>0:return int(year[1])*12,'M'
    text=re.sub(r'(?:个月|個月|月)$',' months',text)
    match = re.fullmatch(r"(\d+)\s*(months?|mos?|m|days?|d)", compact(text), flags=re.I)
    if not match or int(match[1]) <= 0:
        raise ValueError(f"原文期限无法明确解析，需复核: {text!r}")
    return int(match[1]), "M" if match[2].lower().startswith("m") else "D"


def parse_audience(text):
    value = compact(text).casefold()
    # Some transcriptions include the entire row heading and rate. Strip only a
    # syntactically complete interest-rate suffix, never arbitrary trailing text.
    value = re.sub(r":\s*\d+(?:\.\d+)?\s*%\s*p\.?\s*a\.?\s*$", "", value).strip()
    return AUDIENCES.get(value, "unknown")


def parse_channel(text):
    value = compact(text).casefold()
    # Exact source phrases, joined in a fixed order; no inference from URL type.
    channels = []
    if re.search(r"\bonline banking\b", value):
        channels.append("online_banking")
    if re.search(r"\bsc mobile\b", value):
        channels.append("sc_mobile")
    return "|".join(channels) or "unknown"


def dates_in_quote(text):
    months = {name: index for index, name in enumerate(
        ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}
    found = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))
    months.update({name[:3]: value for name, value in list(months.items())})
    for day, month, year in re.findall(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", compact(text)):
        number = months.get(month.casefold())
        if number:
            found.add(date(int(year), number, int(day)).isoformat())
    return found


def check_reference(evidence, pages, lane):
    page = pages.get(evidence.get("page_id"))
    if not page:
        raise ValueError("证据引用必须使用采集器提供的文档ID，不能用截图文件名")
    quote, locator = evidence.get("quote"), evidence.get("locator")
    if not isinstance(quote, str) or not quote.strip() or not isinstance(locator, str) or not locator.strip():
        raise ValueError("证据缺少原文摘录或定位")
    if lane == "llm" and compact(quote) not in compact(page["text"]):
        raise ValueError("原文摘录不是来源中的连续文字；不可改写或拼接")
    if lane == "vlm" and not any(name in locator for name in page.get("images", [])):
        raise ValueError("视觉证据locator未包含该文档对应的截图文件名")


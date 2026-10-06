"""Explicit units, stable identities, and a strict extraction schema."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from .common import digest
import re

def financial_terms(row):
    """Financial bundle fields participate in agreement, beyond free-text prose."""
    if row['product_id']!='maybank-sgd-bundle':return ()
    return tuple((re.search(label+r'\s*([\d.]+)%',row['conditions']).group(1) if re.search(label+r'\s*([\d.]+)%',row['conditions']) else None)
                 for label in ['组合有效年利率：','附加存款比例：'])

# Identity excludes the changing price and expiry, but includes eligibility.
IDENTITY = ("bank", "product_id", "currency", "rate_type", "tenor_value", "tenor_unit",
            "audience", "channel", "amount_min", "amount_max", "min_inclusive",
            "max_inclusive", "amount_currency", "amount_is_equivalent", "fresh_funds",
            "conditions")
FACTS = IDENTITY + ("rate_pct", "rate_basis", "valid_from", "valid_to", "availability")


def dec(value):
    if not isinstance(value, str):
        raise ValueError("金额和利率必须用十进制字符串，利率单位固定为百分数")
    try:
        n = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("非十进制数") from exc
    if not n.is_finite():
        raise ValueError("数值不能是NaN或Infinity")
    return format(n.normalize(), "f")


def normalize(record):
    r = dict(record)
    expected = set(OFFER_SCHEMA["properties"])
    if set(r) != expected:
        raise ValueError(f"记录字段不匹配: missing={expected-set(r)}, extra={set(r)-expected}")
    from .scope import currency_code
    for field in ['currency','amount_currency']:
        if isinstance(r[field],str):r[field]=currency_code(r[field])
    for name, prop in OFFER_SCHEMA["properties"].items():
        value = r[name]
        types = prop.get("type")
        if types == "boolean" and not isinstance(value, bool):
            raise ValueError(f"{name}必须为布尔值")
        if types == "integer" and (type(value) is not int or value <= 0):
            raise ValueError(f"{name}必须为正整数")
        if types == "string" and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{name}必须为非空文本")
        if isinstance(types, list) and value is not None and not isinstance(value, str):
            raise ValueError(f"{name}必须为字符串或null")
        if "enum" in prop and value not in prop["enum"]:
            raise ValueError(f"{name}取值不合法")
    for field in ("rate_pct", "amount_min", "amount_max"):
        if r[field] is not None:
            r[field] = dec(r[field])
    if r["amount_min"] is not None and Decimal(r["amount_min"]) < 0:
        raise ValueError("起存金额不能为负")
    if r["amount_max"] is not None and r["amount_min"] is not None:
        if Decimal(r["amount_max"]) < Decimal(r["amount_min"]):
            raise ValueError("金额上下限倒置")
    for f in ("valid_from", "valid_to"):
        if r[f] is not None:
            date.fromisoformat(r[f])
    if r["valid_from"] and r["valid_to"] and r["valid_from"] > r["valid_to"]:
        raise ValueError("有效期倒置")
    if not isinstance(r["evidence"], list) or not r["evidence"]:
        raise ValueError("每条记录必须提供证据")
    for e in r["evidence"]:
        if set(e) != {"page_id", "quote", "locator"} or not all(isinstance(v, str) and v.strip() for v in e.values()):
            raise ValueError("证据必须包含page_id、quote、locator")
    return r


def key(r):
    return digest({k: r[k] for k in IDENTITY})[:24]


def group_key(r):
    return "/".join(str(r[k]) for k in ("bank", "product_id", "currency", "rate_type", "tenor_value", "tenor_unit"))


def facts(r):
    return {k: r[k] for k in FACTS}


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


S = {"type": "string"}
N = {"type": ["string", "null"]}
BOOL = {"type": "boolean"}
OFFER_SCHEMA = obj({
    "bank": S, "product_id": S, "product_name": S, "currency": S,
    "rate_type": {"type": "string", "enum": ["promo", "board"]},
    "tenor_value": {"type": "integer"},
    "tenor_unit": {"type": "string", "enum": ["M", "D"]},
    "audience": {"type": "string", "enum": ["personal", "preferred", "premier", "private", "premier_elite", "premier_wealth", "premier_standard", "corporate", "all", "unknown"]},
    "channel": S, "amount_min": N, "amount_max": N,
    "min_inclusive": BOOL, "max_inclusive": BOOL,
    "amount_currency": S, "amount_is_equivalent": BOOL,
    "fresh_funds": {"type": "string", "enum": ["yes", "no", "unknown"]},
    "conditions": S, "rate_pct": N,
    "rate_basis": {"type": "string", "enum": ["annual_nominal", "effective", "step", "unknown"]},
    "valid_from": N, "valid_to": N,
    "availability": {"type": "string", "enum": ["available", "withdrawn", "unknown"]},
    "evidence": {"type": "array", "items": obj({"page_id": S, "quote": S, "locator": S})},
})
EXTRACTION_SCHEMA = obj({
    "offers": {"type": "array", "items": OFFER_SCHEMA},
    "coverage_complete": BOOL,
    "unreadable": {"type": "array", "items": S},
    "inventory": {"type": "array", "items": obj({"page_id": S, "row_count": {"type": "integer"}, "notes": S})},
})

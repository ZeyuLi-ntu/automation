"""Deterministic business rules. No model calls or Excel addresses here."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from .schema import group_key, key, facts
from .scope import in_scope,scopes
from .workbook_policy import board_rate_usable

COLORS = {"7D": "E3F2FD", "1M": "E8F4FD", "3M": "E8F5E9", "6M": "FFF8E1",
          "9M": "FCE4EC", "12M": "F3E5F5", "18M": "E0F2F1", "24M": "FFF3E0", "36M": "ECEFF1"}


def display_tenor(offer, config):
    actual = f'{offer["tenor_value"]}{offer["tenor_unit"]}'
    scoped = f'{offer["bank"]}/{offer["product_id"]}/{actual}'
    if scoped in config.get("tenor_map", {}):
        return config["tenor_map"][scoped]
    return actual if actual in COLORS or config.get('allow_actual_tenors') else None


def active(r, as_of):
    return (r["availability"] == "available" and r["rate_pct"] is not None
            and (not r["valid_from"] or r["valid_from"] <= as_of)
            and (not r["valid_to"] or r["valid_to"] >= as_of))


def main_offer(records):
    personal = [r for r in records if r["audience"] == "personal"]
    return max(personal or records, key=lambda r: Decimal(r["rate_pct"]))


def build_views(offers, config, previous_order, as_of, *, include_reference_quotes=False):
    by_group = defaultdict(list)
    for r in offers:
        if active(r, as_of) or (include_reference_quotes and r.get('reference_quote')):
            if not in_scope(r,config):continue
            if r['rate_type']=='board' and not board_rate_usable(r):continue
            by_group[group_key(r)].append(r)
    groups = []
    for identity, records in by_group.items():
        winner = main_offer(records)
        bucket = display_tenor(winner, config)
        if bucket is None:
            raise ValueError(f"没有实际期限归组规则: {identity}")
        # Stable first row is the selected quote; other tiers do not affect group rank.
        details = [winner] + sorted([r for r in records if r is not winner],
                                   key=lambda r: (r["audience"] != "personal", -Decimal(r["rate_pct"]),
                                                  Decimal(r["amount_min"] or "0"), r["channel"]))
        groups.append({"id": identity, "bank": winner["bank"], "product_id": winner["product_id"],
                       "currency":winner['currency'],"rate_type":winner['rate_type'],
                       "product_name": winner["product_name"], "display_tenor": bucket,
                       "main_pct": winner["rate_pct"], "highest_pct": max(records, key=lambda r: Decimal(r["rate_pct"]))["rate_pct"],
                       "winner": winner, "details": details})
    legacy=scopes(config)==[{'currency':'SGD','rate_type':'promo'}]
    def rank_key(g):return ('' if legacy else g['currency']+'/'+g['rate_type']+'/')+g['display_tenor']
    def order(g):
        baseline = previous_order.get(rank_key(g), [])
        return (-Decimal(g["main_pct"]), baseline.index(g["id"]) if g["id"] in baseline else len(baseline),
                g["bank"], g["product_id"], g["id"])
    groups.sort(key=lambda g: (rank_key(g), order(g)))
    rankings = defaultdict(list)
    maxima = {}
    for g in groups:
        rankings[rank_key(g)].append(g["id"])
        k = ('' if legacy else g['currency']+'/'+g['rate_type']+'/')+g["bank"] + "/" + g["display_tenor"]
        best = max(g["details"], key=lambda r: Decimal(r["rate_pct"]))
        if k not in maxima or Decimal(best["rate_pct"]) > Decimal(maxima[k]["rate_pct"]):
            maxima[k] = best
    return {"groups": groups, "order": dict(rankings), "highest": maxima}


def build_updates(offers, previous, config, as_of):
    """Audit all accepted records, including unavailable products excluded from ranks."""
    before, current = defaultdict(list), defaultdict(list)
    for r in previous.get("offers", []):
        before[group_key(r)].append(r)
    for r in offers:
        if in_scope(r,config):
            current[group_key(r)].append(r)
    updates = []
    for identity, rows in sorted(current.items()):
        valid = [r for r in rows if active(r, as_of)]
        old_rows = before.get(identity, [])
        old_valid = [r for r in old_rows if active(r, previous.get("as_of", as_of))]
        winner = main_offer(valid) if valid else rows[0]
        value = winner["rate_pct"] if valid else None
        old_value = main_offer(old_valid)["rate_pct"] if old_valid else None
        if not valid:
            if all(r["availability"] == "withdrawn" for r in rows):
                status = "已停止提供"
            elif all(r["valid_to"] and r["valid_to"] < as_of for r in rows):
                status = "已过期"
            elif all(r["valid_from"] and r["valid_from"] > as_of for r in rows):
                status = "尚未生效"
            else:
                status = "本期未核实，显示-"
        elif not old_rows:
            status = "新增产品或期限" if previous.get("offers") else "首次建档，尚无已发布历史基准"
        elif value != old_value:
            status = "本周已检查，利率调整"
        else:
            status = "本周已检查，利率未调整"
        old_facts = {key(r): {k: v for k, v in facts(r).items() if k != "rate_pct"} for r in old_rows}
        new_facts = {key(r): {k: v for k, v in facts(r).items() if k != "rate_pct"} for r in rows}
        conditions_changed = bool(old_rows) and old_facts != new_facts
        if valid and conditions_changed:
            status += "；条件或有效期变化"
        updates.append({"id": identity, "bank": winner["bank"], "product_id": winner["product_id"],
                        "product_name": winner["product_name"], "display_tenor": display_tenor(winner, config),
                        "actual_tenor": f'{winner["tenor_value"]}{winner["tenor_unit"]}',
                        "main_pct": value, "previous_pct": old_value, "status": status,
                        "conditions_changed": conditions_changed, "details": rows})
    return updates

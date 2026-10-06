from __future__ import annotations

import base64
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from market_rates.common import digest, confined
from market_rates.demo import offer, fixtures, make_demo
from market_rates.store import Store
from market_rates.schema import normalize, key, group_key
from market_rates.rules import main_offer, build_views, display_tenor, active, build_updates
from market_rates.verify import assess, apply_decisions
from market_rates.pipeline import evaluate, live_run, check_evidence
from market_rates.openai_adapter import extract
from market_rates.export import make_plan


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state.sqlite3")
        self.config, self.run = fixtures()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def decisions(self, result, action="llm", persist=False):
        return [{"id": i["id"], "fingerprint": i["fingerprint"], "action": action if i.get("llm") else "acknowledge",
                 "author": "Tester", "reason": "Checked fixture", "persist": persist if i.get("llm") else False}
                for i in result["issues"] if not i["resolved"]]

    def approve(self):
        first = assess(self.run, self.config, self.store)
        apply_decisions(self.run, self.config, self.store, self.decisions(first))
        return assess(self.run, self.config, self.store)


class SchemaTests(unittest.TestCase):
    def test_decimal_normalization(self):
        self.assertEqual(normalize(offer(rate="1.7000"))["rate_pct"], "1.7")

    def test_nan_rejected(self):
        with self.assertRaises(ValueError): normalize(offer(rate="NaN"))

    def test_float_rejected(self):
        with self.assertRaises(ValueError): normalize(offer(rate=1.7))

    def test_identity_ignores_rate_but_not_tier(self):
        self.assertEqual(key(offer()), key(offer(rate="2")))
        self.assertNotEqual(key(offer()), key(offer(audience="premier")))

    def test_zero_is_valid(self):
        self.assertEqual(normalize(offer(rate="0"))["rate_pct"], "0")

    def test_amount_currency_and_boundaries_are_identity(self):
        r = offer(); s = deepcopy(r); s["min_inclusive"] = False
        self.assertNotEqual(key(r), key(s))
        s = deepcopy(r); s["amount_is_equivalent"] = True
        self.assertNotEqual(key(r), key(s))

    def test_invalid_date(self):
        r = offer(); r["valid_to"] = "2026-13-01"
        with self.assertRaises(ValueError): normalize(r)


class RuleTests(unittest.TestCase):
    def test_personal_priority_and_maximum_personal(self):
        rows = [offer(rate="1.5"), offer(rate="1.7"), offer(audience="premier", rate="2")]
        self.assertEqual(main_offer(rows)["rate_pct"], "1.7")

    def test_fallback(self):
        self.assertEqual(main_offer([offer(audience="premier", rate="2"), offer(audience="private", rate="3")])["rate_pct"], "3")

    def test_two_output_metrics_differ(self):
        views = build_views([offer(), offer(audience="premier", rate="1.8")], {}, {}, "2026-09-24")
        self.assertEqual(views["groups"][0]["main_pct"], "1.7")
        self.assertEqual(views["highest"]["DEMO_A/6M"]["rate_pct"], "1.8")

    def test_board_never_in_promo(self):
        r = offer(); r["rate_type"] = "board"
        self.assertFalse(build_views([r], {}, {}, "2026-09-24")["groups"])

    def test_expired_and_future(self):
        self.assertFalse(active(offer(), "2026-10-01"))
        self.assertFalse(active(offer(), "2026-08-31"))

    def test_nonstandard_mapping_is_product_scoped(self):
        r = offer(); r["tenor_value"] = 4
        self.assertIsNone(display_tenor(r, {}))
        self.assertEqual(display_tenor(r, {"tenor_map": {"DEMO_A/demo-a/4M": "3M"}}), "3M")
        r["product_id"] = "other"
        self.assertIsNone(display_tenor(r, {"tenor_map": {"DEMO_A/demo-a/4M": "3M"}}))

    def test_stable_tie_and_new_product(self):
        a = offer(); b = offer("DEMO_B", "demo-b"); c = offer("DEMO_C", "demo-c")
        order = {"6M": [group_key(b), group_key(a)]}
        v = build_views([a,b,c], {}, order, "2026-09-24")
        self.assertEqual(v["order"]["6M"], [group_key(b),group_key(a),group_key(c)])

    def test_precision_before_rounding(self):
        a = offer(rate="1.701"); b = offer("DEMO_B", "demo-b", rate="1.704")
        v = build_views([a,b], {}, {"6M": [group_key(a),group_key(b)]}, "2026-09-24")
        self.assertEqual(v["groups"][0]["bank"], "DEMO_B")

    def test_unchanged_rate_condition_change_reported(self):
        old = offer(); new = deepcopy(old); new["amount_min"] = "50000"
        audit = build_updates([new], {"offers": [old], "as_of": "2026-09-23"}, {}, "2026-09-24")
        self.assertEqual(audit[0]["main_pct"], "1.7")
        self.assertIn("利率未调整", audit[0]["status"])
        self.assertIn("条件或有效期变化", audit[0]["status"])

    def test_withdrawn_retained_for_audit_not_ranking(self):
        old = offer(); new = deepcopy(old); new["availability"] = "withdrawn"; new["rate_pct"] = None
        audit = build_updates([new], {"offers": [old], "as_of": "2026-09-23"}, {}, "2026-09-24")
        self.assertEqual(audit[0]["status"], "已停止提供")
        self.assertIsNone(audit[0]["main_pct"])
        self.assertEqual(audit[0]["previous_pct"], "1.7")
        self.assertFalse(build_views([new], {}, {}, "2026-09-24")["groups"])


class ValidationTests(Base):
    def test_disagreement_and_initial_review(self):
        result = assess(self.run,self.config,self.store)
        self.assertEqual(result["pending"],3)
        self.assertFalse(result["groups"])
        self.assertTrue(any("两路不一致: rate_pct" in i["reasons"] for i in result["issues"]))

    def test_approval_publishes_distinct_metrics(self):
        result = self.approve()
        self.assertEqual(result["pending"],0)
        self.assertEqual(len(result["groups"]),2)
        self.assertEqual(result["highest"]["DEMO_A/6M"]["rate_pct"],"1.8")

    def test_unresolved_cannot_publish(self):
        with self.assertRaises(ValueError): self.store.publish("x","2026-09-24",assess(self.run,self.config,self.store))

    def test_unchanged_agreed_next_run_passes(self):
        result=self.approve();self.store.publish("old","2026-09-23",result)
        self.run["id"]="next";self.run["vlm"]=deepcopy(self.run["llm"])
        self.assertEqual(assess(self.run,self.config,self.store)["pending"],0)

    def test_changed_conditions_not_merged(self):
        self.run["vlm"]["offers"][0]["amount_min"]="50000"
        result=assess(self.run,self.config,self.store)
        self.assertTrue(any("至少一路缺失" in " ".join(i["reasons"]) for i in result["issues"]))

    def test_unique_condition_wording_difference_is_paired_but_blocked(self):
        self.run["vlm"]["offers"][0]["conditions"] = "Different eligibility wording"
        result = assess(self.run, self.config, self.store)
        items = [i for i in result["issues"] if "两路不一致: conditions" in i["reasons"]]
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["llm"] and items[0]["vlm"])
        self.assertFalse(result["offers"])

    def test_multiple_condition_tiers_are_not_arbitrarily_paired(self):
        extra = deepcopy(self.run["llm"]["offers"][0]); extra["conditions"] = "Extra eligibility tier"
        self.run["llm"]["offers"].append(extra)
        self.run["vlm"]["offers"][0]["conditions"] = "Other wording"
        result = assess(self.run, self.config, self.store)
        self.assertFalse(any("两路不一致: conditions" in i["reasons"] for i in result["issues"]))
        self.assertTrue(any("至少一路缺失" in " ".join(i["reasons"]) for i in result["issues"]))

    def test_missing_clause_blocks_even_previously_approved_quotes(self):
        self.approve()
        self.run["metadata"] = [{"lane": "llm", "clause_ledger": [{"page_id": "DEMO_A", "number": 1,
                                      "quote": "Account required.", "locator": "Clause 1"}]}]
        result = assess(self.run, self.config, self.store)
        self.assertTrue(any(i["id"].startswith("clause:") for i in result["issues"]))
        self.assertFalse(result["offers"])

    def test_evidence_quote_failure(self):
        self.run["llm"]["offers"][0]["evidence"][0]["quote"]="invented quote"
        result=assess(self.run,self.config,self.store)
        self.assertTrue(any("LLM原文摘录不能在采集文字中定位" in i["reasons"] for i in result["issues"]))

    def test_missing_coverage_blocks_all_groups(self):
        self.approve();self.run["llm"]["coverage_complete"]=False
        result=assess(self.run,self.config,self.store)
        self.assertTrue(result["pending"])
        self.assertFalse(result["groups"])

    def test_persistent_override_does_not_resolve_new_conflict(self):
        self.store.set_override(key(normalize(offer())),{"rate_pct":"1.9"},"Tester","Correction")
        first=assess(self.run,self.config,self.store)
        item=next(i for i in first["issues"] if i["id"]==key(normalize(offer())))
        self.assertEqual(item["effective"]["rate_pct"],"1.9")
        self.assertFalse(item["resolved"])

    def test_persist_decision_remains_resolved(self):
        result=assess(self.run,self.config,self.store)
        item=next(i for i in result["issues"] if i["id"]==key(normalize(offer())))
        fixed=deepcopy(item["effective"]);fixed["rate_pct"]="1.9"
        apply_decisions(self.run,self.config,self.store,[{"id":item["id"],"fingerprint":item["fingerprint"],"action":"replace",
                        "offer":fixed,"author":"Tester","reason":"Correction","persist":True}])
        second=assess(self.run,self.config,self.store)
        updated=next(i for i in second["issues"] if i["id"]==item["id"])
        self.assertTrue(updated["resolved"])
        self.assertEqual(self.store.overrides()[item["id"]]["rate_pct"],"1.9")

    def test_missing_current_keeps_unknown_not_withdrawn(self):
        result=self.approve();self.store.publish("old","2026-09-23",result)
        self.run["id"]="next"
        self.run["llm"]["offers"]=[];self.run["vlm"]["offers"]=[]
        result=assess(self.run,self.config,self.store)
        self.assertTrue(any(i.get("effective",{}).get("availability")=="unknown" for i in result["issues"] if i.get("effective")))

    def test_stale_decision_rejected(self):
        result=assess(self.run,self.config,self.store); entries=self.decisions(result)
        self.run["evidence_hash"]="changed"
        with self.assertRaises(ValueError):apply_decisions(self.run,self.config,self.store,entries)

    def test_override_revoke_auditable(self):
        k=key(offer());self.store.set_override(k,{"rate_pct":"2"},"T","fix")
        self.store.set_override(k,{},"T","remove",active=False)
        self.assertNotIn(k,self.store.overrides())
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM overrides").fetchone()[0],2)

    def test_demo_creates_review_and_preview(self):
        first,last=make_demo(self.root/"demo",self.store)
        self.assertEqual(first["pending"],3);self.assertEqual(last["pending"],0)
        self.assertTrue((self.root/"demo/review.html").exists())
        self.assertIn("1.7%",(self.root/"demo/resolved-example/rainbow.preview.html").read_text(encoding="utf8"))

    def test_source_failures_block(self):
        self.run["errors"]=["DEMO_A page failed"]
        result=assess(self.run,self.config,self.store)
        self.assertTrue(any(i["id"].startswith("source:") for i in result["issues"]))

    def test_duplicate_records_block(self):
        self.run["llm"]["offers"].append(deepcopy(self.run["llm"]["offers"][0]))
        result=assess(self.run,self.config,self.store)
        self.assertTrue(any("相同身份重复报价" in " ".join(i["reasons"]) for i in result["issues"]))

    def test_row_count_disagreement_requires_review(self):
        self.run["vlm"]["inventory"][0]["row_count"] = 1
        result = assess(self.run, self.config, self.store)
        self.assertTrue(any(i["id"].startswith("row-count:") for i in result["issues"]))

    def test_missing_expected_tenor_blocks(self):
        self.config["products"][0]["expected_tenors"] = ["6M", "12M"]
        result = assess(self.run, self.config, self.store)
        self.assertEqual(sum(i["id"].startswith("tenor-missing:") for i in result["issues"]), 2)

    def test_expired_personal_does_not_silently_enable_premier(self):
        self.run["llm"]["offers"][0]["valid_to"] = "2026-09-23"
        self.run["vlm"]["offers"][0]["valid_to"] = "2026-09-23"
        first = assess(self.run, self.config, self.store)
        apply_decisions(self.run, self.config, self.store, self.decisions(first))
        result = assess(self.run, self.config, self.store)
        item = next(i for i in result["issues"] if i["id"].startswith("personal-missing:"))
        self.assertFalse(item["resolved"])
        self.assertFalse(any(g["bank"] == "DEMO_A" for g in result["groups"]))
        apply_decisions(self.run, self.config, self.store, [{"id": item["id"], "fingerprint": item["fingerprint"],
                        "action": "acknowledge", "author": "Tester", "reason": "Confirmed Personal expired; fallback is appropriate"}])
        self.assertEqual(assess(self.run, self.config, self.store)["pending"], 0)

    def test_live_past_date_rejected_before_browser(self):
        with self.assertRaises(ValueError):live_run(self.config,self.root/"live","2000-01-01",self.store)

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):confined(self.root,"../private")


class AdapterTests(unittest.TestCase):
    def test_missing_configuration(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaises(ValueError):extract("llm",[],Path('.'),{},"2026-09-24")

    def test_legacy_cloud_entry_rejects_even_configured_keys(self):
        with patch.dict("os.environ",{"OPENAI_API_KEY":"test","OPENAI_TEXT_MODEL":"text-model","OPENAI_VISION_MODEL":"vision-model"}),patch("urllib.request.urlopen") as call:
            for lane in ['llm','vlm']:
                with self.assertRaisesRegex(ValueError,'云端模型入口已禁用'):
                    extract(lane,[],Path('.'),{'models':{'provider':'openai'}},'2026-09-24')
            call.assert_not_called()


if __name__ == "__main__": unittest.main()

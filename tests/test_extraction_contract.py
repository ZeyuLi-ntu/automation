"""Synthetic values deliberately differ from the frozen SCB benchmark."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_rates.extraction_contract import response_schema, parse_tenor, parse_audience, check_reference
from market_rates.scb_extractor import (bind_unit, bind_terms_text, combine, parse_rate, parse_money,
                                        parse_period, extract, TABLE_INSTRUCTIONS, PDF_INSTRUCTIONS)
from market_rates.clause_review import clause_differences


class LiteralExtractionTests(unittest.TestCase):
    def setUp(self):
        self.product = {"id": "scb-sgd-fresh-funds", "bank": "SCB", "name": "Synthetic deposit"}
        self.config = {"products": [self.product], "models": {"max_images": 3, "num_ctx": 32768}}
        self.web = {"id": "web-id", "bank": "SCB", "images": ["web-shot.png"], "text":
                    "9 months Personal Banking: 3.25% p.a. S$12,000 SGD Online Banking or SC Mobile "
                    "From 02 January 2027 to 31 January 2027"}
        self.pdf = {"id": "pdf-id", "bank": "SCB", "images": ["terms-p1.png", "terms-p2.png"],
                    "capture_scope": "pdf", "url": "https://example.invalid/singapore-dollar-time-deposit-tnc.pdf",
                    "text": "[PDF page 1]\n1. From 06 January 2027 to 31 January 2027.\n"
                    "2. Fresh funds are funds that do not originate here and are not re-deposited within 19 days.\n"
                    "3. Priority Banking status must be maintained at all times.\n[PDF page 2]\n4. Other terms apply."}
        self.unit = {"page": self.web, "text": self.web["text"], "label": "web-shot.png"}
        self.raw = {"rows": [{"product_id": self.product["id"], "tenor_text": "9 months",
                     "audience_text": "Personal Banking", "rate_text": "3.25% p.a.", "minimum_text": "S$12,000",
                     "minimum_inclusive": True, "maximum_text": None, "maximum_inclusive": False,
                     "currency_text": "SGD", "availability": "available", "locator": "table"}],
                    "channels": [{"product_id": self.product["id"], "quote": "Online Banking or SC Mobile", "locator": "heading"}],
                    "periods": [{"product_id": self.product["id"], "quote": "From 02 January 2027 to 31 January 2027", "locator": "heading"}],
                    "terms": [], "coverage_complete": True, "unreadable": []}

    def test_original_tenor_and_customer_identity(self):
        self.assertEqual(parse_tenor("9 months"), (9, "M"))
        self.assertEqual(parse_tenor("180 days"), (180, "D"))
        for label, expected in [("Personal Banking: 3.25% p.a.", "personal"), ("Priority Banking", "preferred"),
                                ("Priority Private", "private"), ("individuals", "unknown")]:
            self.assertEqual(parse_audience(label), expected)
        with self.assertRaises(ValueError): parse_tenor("about half a year")

    def test_combined_rates_and_wrong_money_are_rejected(self):
        for value in ["3.25% p.a. 4.25% p.a.", "3.25", "3.25% monthly"]:
            with self.subTest(value=value), self.assertRaises(ValueError): parse_rate(value)
        for value in ["US$12,000", "S$12,00", "about 12000"]:
            with self.subTest(value=value), self.assertRaises(ValueError): parse_money(value)
        self.assertEqual(parse_money("S$12,000"), "12000")

    def test_heading_rate_cannot_conflict_with_rate_field(self):
        self.raw["rows"][0]["audience_text"] = "Personal Banking: 9.25% p.a."
        with self.assertRaisesRegex(ValueError, "报价不一致"): bind_unit(self.raw, self.unit, "vlm")

    def test_unknown_evidence_and_inexact_text_rejected(self):
        for reference in [{"page_id": "web-shot.png", "quote": "9 months", "locator": "web-shot.png table"},
                          {"page_id": "web-id", "quote": "9 months ... Personal Banking", "locator": "table"}]:
            with self.assertRaises(ValueError): check_reference(reference, {"web-id": self.web}, "llm")

    def test_references_bound_by_caller_and_vision_does_not_read_text(self):
        self.unit.pop("text")
        self.unit["page"]["text"] = None
        bound = bind_unit(self.raw, self.unit, "vlm")
        for reference in bound["rows"][0]["evidence"]:
            self.assertEqual(reference["page_id"], "web-id")
            self.assertIn("web-shot.png", reference["locator"])
        with self.assertRaises(ValueError):
            check_reference({"page_id": "web-id", "quote": "SGD", "locator": "terms-p1.png"}, {"web-id": self.web}, "vlm")

    def test_combine_preserves_conflicting_dates_and_tier_conditions(self):
        text = self.pdf["text"].split("[PDF page 2]")[0]
        pdf_unit = {"page": self.pdf, "text": text, "label": "pdf-text-page1"}
        terms = bind_terms_text(text, [], pdf_unit, "llm", [self.product])
        table = bind_unit(self.raw, self.unit, "llm")
        priority = deepcopy(table["rows"][0]); priority["audience_text"] = "Priority Private"
        table["rows"].append(priority)
        result, audit = combine([(self.unit, table), (pdf_unit, terms)], [self.web, self.pdf], self.config)
        personal, private = result["offers"]
        self.assertEqual((personal["tenor_value"], personal["tenor_unit"], personal["rate_pct"]), (9, "M", "3.25"))
        self.assertEqual(personal["channel"], "online_banking|sc_mobile")
        self.assertIsNone(personal["valid_from"])
        self.assertEqual(personal["valid_to"], "2027-01-31")
        self.assertNotIn("Priority Banking status", personal["conditions"])
        self.assertIn("Priority Banking status", private["conditions"])
        self.assertEqual(len(audit["source_periods"]), 2)
        self.assertTrue(any("来源日期冲突" in s for s in audit["review_required"]))

    def test_period_must_have_two_explicit_ordered_dates(self):
        self.assertEqual(parse_period("06 January 2027 to 31 January 2027"), ("2027-01-06", "2027-01-31"))
        for text in ["until 31 January 2027", "31 January 2027 to 06 January 2027"]:
            with self.assertRaises(ValueError): parse_period(text)

    def test_full_clauses_preserved_and_footer_excluded(self):
        text = "1. You must qualify; and\nb. keep the account.\n2. Second clause.\nPUBLIC\nFooter."
        unit = {"page": self.pdf, "image": "terms-p1.png", "label": "terms-p1.png"}
        result = bind_terms_text(text, [], unit, "vlm", [self.product])
        self.assertIn("; and b.", result["clause_ledger"][0]["quote"])
        self.assertEqual(result["clause_ledger"][1]["quote"], "Second clause.")
        self.assertEqual(result["rows"], [])

    def test_missing_internal_clause_is_flagged(self):
        unit = {"page": self.pdf, "label": "terms-p1.png"}
        result = bind_terms_text("1. First.\n3. Third.", [], unit, "vlm", [self.product])
        self.assertFalse(result["coverage_complete"])
        self.assertTrue(result["unreadable"])

    def test_generic_schema_binds_document_ids_without_answer_values(self):
        schema = response_schema([self.web, self.pdf])
        self.assertEqual(schema["properties"]["offers"]["items"]["properties"]["evidence"]["items"]["properties"]["page_id"]["enum"], ["web-id", "pdf-id"])
        self.assertNotIn("1.70", TABLE_INSTRUCTIONS + PDF_INSTRUCTIONS)

    def test_full_visual_lane_receives_every_image_and_no_text_or_other_answers(self):
        table = {k: deepcopy(self.raw[k]) for k in ("rows", "channels", "periods", "unreadable")}
        table["other_conditions"] = []
        bodies = [table, {"text": "1. From 06 January 2027 to 31 January 2027.", "unreadable": []},
                  {"text": "2. Other terms.", "unreadable": []}]
        responses = [{"done": True, "done_reason": "stop", "message": {"content": json.dumps(b)}} for b in bodies]
        self.web["text"] = self.pdf["text"] = "TEXT_LANE_SECRET_SENTINEL"
        with tempfile.TemporaryDirectory() as temp:
            evidence = Path(temp) / "evidence"; evidence.mkdir()
            for page in [self.web, self.pdf]:
                for name in page["images"]: (evidence / name).write_bytes(b"\x89PNG\r\n\x1a\n" + name.encode())
            with patch("market_rates.ollama_adapter.check_model"), patch("market_rates.ollama_adapter.request_json", side_effect=responses) as request:
                result, metadata = extract("vlm", [self.web, self.pdf], evidence, self.config, "2027-01-12")
            self.assertEqual(request.call_count, 3)
            self.assertEqual(len(metadata["units"]), 3)
            self.assertEqual(len(result["offers"]), 1)
            for call in request.call_args_list:
                payload = call.args[2]
                self.assertNotIn("TEXT_LANE_SECRET_SENTINEL", json.dumps(payload))
                self.assertEqual(len(payload["messages"][1]["images"]), 1)


class ClauseReviewTests(unittest.TestCase):
    def metadata(self, left, right):
        return [{"lane": lane, "clause_ledger": [{"page_id": "p", "number": 2, "quote": quote, "locator": lane}]}
                for lane, quote in [("llm", left), ("vlm", right)]]

    def test_typography_can_match_but_missing_conjunction_cannot(self):
        self.assertEqual(clause_differences(self.metadata("Bank’s rule; and\naccount.", "Bank's rule; and account.")), [])
        self.assertEqual(len(clause_differences(self.metadata("Rule; and account.", "Rule; account."))), 1)

    def test_missing_or_duplicate_clause_requires_review(self):
        metadata = self.metadata("a", "a")
        metadata[1]["clause_ledger"] = []
        self.assertEqual(len(clause_differences(metadata)), 1)
        metadata[1]["clause_ledger"] = metadata[0]["clause_ledger"] * 2
        self.assertEqual(len(clause_differences(metadata)), 1)

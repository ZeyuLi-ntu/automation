import ast
import unittest
from decimal import Decimal
from pathlib import Path

from market_rates.board_wave import normalize_section
from market_rates.workbook_policy import board_rate_usable
from market_rates.rules import active
from market_rates.board_plan import amount
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, PAGE_SETTLE_MS


class BoardUserPolicyTests(unittest.TestCase):
    def section(self, **values):
        return dict(id='source', page_id='page', product_id='board', table=0, **values)

    def test_percent_policy_preserves_unstated_source_basis(self):
        r={'rate_type':'board','rate_basis':'unknown'}
        self.assertTrue(board_rate_usable(r))
        self.assertEqual(r['rate_basis'],'unknown')
        self.assertFalse(board_rate_usable(r,{'board_rate_unit':'unconfirmed'}))
        self.assertFalse(board_rate_usable(dict(r,rate_type='promo')))
        self.assertFalse(board_rate_usable(dict(r,rate_basis='step')))

    def test_hlf_unmarked_numbers_are_not_multiplied_by_100(self):
        s=self.section(bank='HLF',currency='SGD',rows=[['Tenure (Months)','Board Rates (<= S$50,000)','Special Rates (> S$50,000)'],['1','0.050','0.125'],['3','0.100','0.150']])
        rs=normalize_section(s,'llm')
        self.assertEqual([r['rate_pct'] for r in rs],['0.05','0.125','0.1','0.15'])
        self.assertEqual(Decimal(rs[0]['rate_pct'])/100,Decimal('0.0005'))
        self.assertEqual([(r['amount_min'],r['amount_max']) for r in rs],[('10000','50000'),('50000','1000000'),('500','50000'),('50000','1000000')])
        self.assertTrue(rs[0]['max_inclusive']);self.assertFalse(rs[1]['min_inclusive'])
        self.assertTrue(all(board_rate_usable(r) for r in rs))

    def test_icbc_sgd_board_columns_and_exclusive_bounds(self):
        s=self.section(bank='ICBC',currency='SGD',layout='icbc-board',rows=[['Amount (SGD)/Tenor','1 month','3 months','6 months','9 months','12 months'],['500-5,000 (exclusive)','0.95%','1.15%','1.20%','0.90%','0.90%']])
        rs=normalize_section(s,'vlm')
        self.assertEqual([(r['tenor_value'],r['rate_pct']) for r in rs],[(1,'0.95'),(3,'1.15'),(6,'1.2'),(9,'0.9'),(12,'0.9')])
        self.assertTrue(all(r['amount_min']=='500' and r['amount_max']=='5000' and not r['max_inclusive'] for r in rs))

    def test_icbc_cny_retains_tab_currency_and_minimum(self):
        s=self.section(bank='ICBC',currency='CNY',layout='icbc-board',minimum='500',rows=[['Amount (RMB)','1 Month'],['Below 50k(exclusive)','1.10%'],['50k(inclusive)&Above','1.15%']])
        rs=normalize_section(s,'llm')
        self.assertEqual([(r['currency'],r['amount_min'],r['amount_max'],r['rate_pct']) for r in rs],[('CNY','500','50000','1.1'),('CNY','50000',None,'1.15')])

    def test_icbc_usd_never_borrows_promotional_minimum(self):
        s=self.section(bank='ICBC',currency='USD',layout='icbc-board',minimum='500',rows=[['Amount (USD)','1 Month'],['Below 100k(exclusive)','3.50%'],['100K(inclusive) and above','3.60%']])
        rs=normalize_section(s,'llm')
        self.assertIsNone(rs[0]['amount_min']);self.assertEqual(rs[0]['amount_max'],'100000')
        self.assertEqual(rs[1]['amount_min'],'100000')
        self.assertIn('USD <100,000',amount(rs[0]));self.assertNotIn('≥500',amount(rs[0]))

    def test_quote_date_and_effective_date_are_different(self):
        s=self.section(bank='HSBC',currency='AUD',layout='hsbc-fx-pdf',audience='personal',source_date='2026-09-29',rows=[['Australian Dollar AUD'],['Placement Amount / Term','1 Month'],['AUD25,000 to AUD49,999','2.50%']])
        r=normalize_section(s,'llm')[0]
        self.assertIsNone(r['valid_from']);self.assertTrue(active(r,'2026-09-28'))
        self.assertTrue(any(e['quote']=='Rates as at: 2026-09-29' for e in r['evidence']))
        self.assertFalse(active(dict(r,valid_from='2026-09-29'),'2026-09-28'))

    def test_all_browser_navigation_uses_long_wait(self):
        root=Path(__file__).resolve().parents[1];calls=0
        for folder in ['scripts','market_rates']:
            for file in (root/folder).glob('*.py'):
                tree=ast.parse(file.read_text(encoding='utf-8-sig'))
                for call in ast.walk(tree):
                    if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Attribute) or call.func.attr!='goto':continue
                    calls+=1
                    timeout=next((k.value for k in call.keywords if k.arg=='timeout'),None)
                    self.assertIsInstance(timeout,ast.Name,str(file))
                    self.assertEqual(timeout.id,'PAGE_LOAD_TIMEOUT_MS',str(file))
        self.assertGreaterEqual(calls,19)
        self.assertGreaterEqual(PAGE_LOAD_TIMEOUT_MS,120000)
        self.assertGreaterEqual(CONTENT_TIMEOUT_MS,90000)
        self.assertGreaterEqual(PAGE_SETTLE_MS,5000)

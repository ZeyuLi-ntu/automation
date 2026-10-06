import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from market_rates.common import save,load
from market_rates.board_wave import replace_verified_sections
from market_rates.board_wave import normalize_section,tenor_values
from scripts.verify_board_wave import canonical_transcription
from market_rates.rules import active,main_offer
from scripts.capture_board_repairs import effective_date,source_confirmation

class BoardRepairTests(unittest.TestCase):
    def base(self,**kwargs):
        return dict(id='source-table',page_id='source',product_id='test-board',table=0,**kwargs)

    def test_bea_personal_corporate_equivalent_minimum(self):
        s=self.base(bank='BEA',currency='FX',layout='bea-fx',rate_basis='annual_nominal',rows=[['Currency','Rate (% p.a.)'],['Minimum (Equivalent) Personal / Corporate','1 week','1 month'],['Renminbi','CNY','USD10K/20K','0.25','0.60']])
        rows=normalize_section(s,'llm')
        self.assertEqual(len(rows),4)
        personal=[r for r in rows if r['audience']=='personal']
        self.assertTrue(all(r['amount_min']=='10000' and r['amount_currency']=='USD' and r['amount_is_equivalent'] for r in personal))
        self.assertTrue(all(r['amount_min']=='20000' for r in rows if r['audience']=='corporate'))
        self.assertEqual(main_offer(rows)['audience'],'personal')
        self.assertEqual(tenor_values('1 week'),[(7,'D')])

    def test_bea_unsorted_amount_headers_stay_attached(self):
        s=self.base(bank='BEA',currency='SGD',layout='bea-sgd',rate_basis='annual_nominal',rows=[['Terms','Rate (% p.a.)'],['$1,000-$49,999.99','$100,000-$249,999.99','$50,000-$99,999.99'],['1 month','0.1250','0.2500','0.3000']])
        rs=normalize_section(s,'vlm')
        self.assertEqual([(r['amount_min'],r['rate_pct']) for r in rs],[('1000','0.125'),('100000','0.25'),('50000','0.3')])

    def test_hsbc_pdf_continuation_and_quote_date(self):
        s=self.base(bank='HSBC',currency='CAD',layout='hsbc-fx-pdf',audience='personal',valid_from='2026-09-29',rows=[['Canadian Dollar CAD'],['Placement Amount / Term','1 Month','3 Month'],['CAD25,000 to\nCAD49,999','0.25%','0.50%'],['CAD1,000,000 and above','0.75%','1.00%']])
        rows=normalize_section(s,'llm');self.assertEqual(len(rows),4)
        self.assertEqual(rows[-1]['amount_min'],'1000000');self.assertIsNone(rows[-1]['amount_max'])
        self.assertIsNone(rows[0]['valid_from']);self.assertTrue(active(rows[0],'2026-09-28'))
        self.assertTrue(any(e['locator'].endswith('/source-date') and '2026-09-29' in e['quote'] for e in rows[0]['evidence']))

    def test_cimb_amount_points_do_not_invent_ranges(self):
        s=self.base(bank='CIMB',currency='FX',amount_mode='quoted_point',rows=[['Tenure (Month)','10k','50k'],['1','N/A','0.07'],['3','0.24','0.37']])
        rows=normalize_section(s,'llm');self.assertEqual(len(rows),3)
        self.assertTrue(all(r['amount_min']==r['amount_max'] and r['max_inclusive'] for r in rows))
        self.assertTrue(all(r['rate_basis']=='unknown' for r in rows))

    def test_scb_separator_alias_never_changes_financial_digits(self):
        t=dict(kind='grid',comparison_profile='scb-range-separator')
        expected=canonical_transcription([['25,000 T0 49,999','2.4870']],t)
        self.assertEqual(expected,canonical_transcription([['25,000 TO 49,999','2.4870']],t))
        self.assertNotEqual(expected,canonical_transcription([['25,000 TO 49,999','2.4879']],t))
        self.assertNotEqual(expected,canonical_transcription([['25,100 TO 49,999','2.4870']],t))

    def test_unit_confirmation_is_limited_to_confirmed_sources(self):
        self.assertEqual(source_confirmation('SCB','FX','https://www.sc.com/sg/help/faqs/foreign-currency-interest-rates/')['rate_basis'],'annual_nominal')
        self.assertIsNone(source_confirmation('SCB','SGD','https://www.sc.com/sg/help/faqs/foreign-currency-interest-rates/'))
        self.assertIsNone(source_confirmation('CITI','FX','https://www.sc.com/sg/help/faqs/foreign-currency-interest-rates/'))
        self.assertIsNone(source_confirmation('SCB','FX','https://example.com/sg/help/faqs/foreign-currency-interest-rates/'))

    def test_maybank_date_is_not_hardcoded(self):
        self.assertEqual(effective_date('Effective from: 2 October 2026'),'2026-10-02')
        with self.assertRaises(ValueError):effective_date('Date unavailable')

    def test_bea_tier_preserves_real_currency_threshold(self):
        s=self.base(bank='BEA',currency='FX',layout='bea-fx',rate_basis='annual_nominal',rows=[['Currency','Rate (% p.a.)'],['Minimum','1 month'],['Australian Dollar','AUD','100,000','3.8700']]);s.update(product_id='bea-fx-tier',table=1)
        r=normalize_section(s,'llm')[0]
        self.assertEqual((r['amount_currency'],r['amount_min'],r['audience']),('AUD','100000','all'))
        self.assertFalse(r['amount_is_equivalent'])

    def test_refresh_replaces_only_enrolled_products_without_duplicates(self):
        old=self.base(bank='SCB',currency='FX',rows=[['GBP','1 MTH'],['5,000 TO 24,999','2.00']]);old['table']=1
        fresh=dict(old,rate_basis='annual_nominal',rows=[['GBP','1 MTH'],['5,000 TO 24,999','2.50']])
        usd=dict(old,table=0)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base=root/'base';wave=root/'wave'
            for folder in [base,wave]:(folder/'evidence').mkdir(parents=True)
            prior=dict(id='base',as_of='2026-09-27',pages=[],bank_dates={'SCB':'2026-09-27'},coverage=[dict(bank='SCB',currency='FX',section='scb-fx-board-1',reason='failed')],wide_sources=[],llm=dict(offers=normalize_section(old,'llm')+normalize_section(usd,'llm')),vlm=dict(offers=normalize_section(old,'vlm')+normalize_section(usd,'vlm')))
            for lane in ['llm','vlm']:prior[lane]['offers'].append(dict(prior[lane]['offers'][-1],channel='online'))
            save(base/'run.json',prior)
            newer=dict(as_of='2026-09-28',pages=[],bank_dates={'SCB':'2026-09-28'},sections=[fresh],coverage=[])
            with patch('market_rates.board_wave.validate_wave',return_value=newer):r=replace_verified_sections(base,wave,root/'out')
            self.assertEqual(len(r['llm']['offers']),3)
            self.assertEqual({x['currency']:x['rate_pct'] for x in r['llm']['offers']},{'USD':'2','GBP':'2.5'})
            self.assertEqual(r['coverage'],[]);self.assertEqual(load(base/'run.json'),prior)

if __name__=='__main__':unittest.main()

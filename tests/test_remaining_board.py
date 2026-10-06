import unittest
from market_rates.remaining_board import normalize_remaining
from market_rates.board_freshness import compare_publication_dates
from scripts.verify_board_wave import canonical_transcription

class RemainingBoardTests(unittest.TestCase):
    def s(self,bank,currency,layout,rows,**kw):return dict(id='source',page_id='page',product_id=bank.lower()+'-'+currency.lower()+'-board',bank=bank,currency=currency,layout=layout,rows=rows,**kw)
    def test_uob_offshore_cny_and_weekly_minima(self):
        s=self.s('UOB','USD','uob-fx',[['Currency','1 Wk','1 Mth'],['US DOLLAR'],['Below 50,000','0.0000','3.3400'],['50,000 - 99,999','2.3700','3.4400']])
        r=normalize_remaining(s,'llm');self.assertEqual([(x['tenor_value'],x['tenor_unit'],x['amount_min']) for x in r],[(7,'D','25000'),(1,'M','5000'),(7,'D','50000'),(1,'M','50000')]);self.assertEqual(r[0]['rate_pct'],'0')
        s=self.s('UOB','CNH','uob-fx',[['Currency','1 Mth'],['CHINESE RENMINBI (OFFSHORE)'],['250,000 - 499,999','0.9000']])
        r=normalize_remaining(s,'vlm')[0];self.assertEqual((r['currency'],r['amount_min'],r['rate_pct']),('CNH','250000','0.9'))
    def test_dbs_currency_tiers_not_sgd_equivalent_minimum(self):
        s=self.s('DBS','USD','dbs-fx',[['Amt(USD)','1 day','1 week','3 mths'],["< 10'000",'0.0000','0.0000','3.7800'],["<= 100'000",'0.0000','0.0000','3.7800']])
        r=normalize_remaining(s,'llm');self.assertEqual(len(r),4);self.assertIsNone(r[0]['amount_min']);self.assertEqual(r[0]['amount_max'],'10000');self.assertEqual(r[1]['amount_min'],'50000');self.assertEqual(r[1]['rate_pct'],'0');self.assertEqual(r[3]['amount_min'],'10000');self.assertTrue(r[3]['max_inclusive']);self.assertIn('SGD5,000等值',r[0]['conditions'])
    def test_rhb_upper_tier_is_not_exact_amount(self):
        s=self.s('RHB','CNY','rhb-fx',[['Currency','1-wk','1-mth','3-mth'],['Chinese Yuan - Offshore (CNY)','–','0.35','0.45']],band='Up to 99,999')
        r=normalize_remaining(s,'llm');self.assertEqual(len(r),2);self.assertIsNone(r[0]['amount_min']);self.assertEqual(r[0]['amount_max'],'99999');self.assertTrue(r[0]['max_inclusive']);self.assertEqual(r[1]['rate_pct'],'0.45')
    def test_sbi_old_still_published_date_and_threshold(self):
        s=self.s('SBI','GBP','sbi-fx',[['GBP deposit rates with effect from 01.Oct.2024'],['10,000 to 1,000,000'],['Period','Fixed *'],['3 month','0.1000']],source_date='2024-10-01',valid_from='2024-10-01')
        r=normalize_remaining(s,'vlm')[0];self.assertEqual(r['rate_pct'],'0.1');self.assertEqual(r['valid_from'],'2024-10-01');self.assertEqual(r['amount_min'],'10000')
    def test_cimb_short_minimum_and_distinct_product(self):
        s=self.s('CIMB','SGD','cimb-sgd',[['Tenure (Months)','Board Rates (% p.a.)\nS$1,000 - $99,999'],['1*','0.20'],['3','0.30']],islamic=False)
        r=normalize_remaining(s,'llm');self.assertEqual([o['amount_min'] for o in r],['5000','1000']);self.assertEqual(r[0]['amount_max'],'99999')
    def test_missing_dash_typography_only(self):
        f=lambda x:canonical_transcription([[x]],{'kind':'grid'})
        self.assertEqual(f('–'),f('-'));self.assertEqual(f('—'),f('-'))
        self.assertNotEqual(f('0'),f('-'));self.assertNotEqual(f('-0.1'),f('0.1'))
    def test_merged_heading_and_currency_punctuation_never_hide_numeric_errors(self):
        t=dict(kind='grid',merged_caption_rows=[0])
        f=lambda value:canonical_transcription(value,t)
        self.assertEqual(f([['US DOLLAR']]*1+[['0','3.20']]),f([['US DOLLAR']*8,['0','3.20']]))
        self.assertNotEqual(f([['US DOLLAR'],['0','3.20']]),f([['AUSTRALIAN DOLLAR']*8,['0','3.20']]))
        self.assertNotEqual(f([['US DOLLAR'],['0','3.20']]),f([['US DOLLAR']*8,['0','3.21']]))
        t=dict(kind='grid',comparison_profile='cimb-sgd-dollar-sign')
        self.assertEqual(canonical_transcription([['S$1,000 - $99,999']],t),canonical_transcription([['S$1,000 - S$99,999']],t))
        self.assertNotEqual(canonical_transcription([['S$1,000 - $99,999']],t),canonical_transcription([['US$1,000 - $99,999']],t))
    def quote(self,date):
        return dict(bank='SBI',currency='GBP',product_id='sbi-gbp-board',valid_from=date,valid_to=None,availability='available',evidence=[])
    def test_latest_publication_compares_with_previous_not_today(self):
        a=self.quote('2024-10-01');b=self.quote('2025-01-01')
        retain,events=compare_publication_dates([a],[b],'2026-09-28');self.assertFalse(retain);self.assertEqual(events[0]['status'],'newer')
        retain,events=compare_publication_dates([a],[a],'2026-09-28');self.assertFalse(retain);self.assertEqual(events[0]['status'],'unchanged_date')
    def test_regressed_source_keeps_later_unexpired_quote(self):
        retain,events=compare_publication_dates([self.quote('2026-09-25')],[self.quote('2026-09-20')],'2026-09-28');self.assertEqual(len(retain),1);self.assertTrue(events[0]['retained_previous'])
        old=dict(self.quote('2026-09-25'),valid_to='2026-09-26')
        retain,_=compare_publication_dates([old],[self.quote('2026-09-20')],'2026-09-28');self.assertFalse(retain)
    def test_first_capture_accepts_old_publication(self):
        retain,events=compare_publication_dates([],[self.quote('2024-10-01')],'2026-09-28');self.assertFalse(retain);self.assertEqual(events[0]['status'],'first_observation')
    def test_batch_date_reconciliation_keeps_evidence_but_never_fills_missing_scopes(self):
        import tempfile
        from pathlib import Path
        from market_rates.common import save,load,digest
        from market_rates.board_freshness import reconcile_run_dates
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp)/'old';new=Path(tmp)/'new';missing=Path(tmp)/'missing'
            old_offer=dict(self.quote('2026-09-25'),rate_pct='0.1')
            new_offer=dict(self.quote('2026-09-20'),rate_pct='0.05')
            for folder,rows in [(old,[old_offer]),(new,[new_offer]),(missing,[])]:
                (folder/'evidence').mkdir(parents=True)
                save(folder/'run.json',dict(as_of='2026-09-28',pages=[],evidence_hash=digest([]),wide_sources=[],llm=dict(offers=rows),vlm=dict(offers=rows)))
            (old/'evidence'/'old-source.txt').write_text('archived source')
            reconcile_run_dates(old,new);r=load(new/'run.json')
            for lane in ['llm','vlm']:self.assertEqual(r[lane]['offers'][0]['rate_pct'],'0.1')
            self.assertTrue(r['source_date_events'][0]['retained_previous'])
            self.assertEqual((new/'evidence'/'old-source.txt').read_text(),'archived source')
            reconcile_run_dates(old,missing)
            self.assertEqual(load(missing/'run.json')['llm']['offers'],[])
    def test_future_effective_quote_not_carried_backwards(self):
        retain,_=compare_publication_dates([self.quote('2026-09-30')],[self.quote('2026-09-28')],'2026-09-28')
        self.assertFalse(retain)

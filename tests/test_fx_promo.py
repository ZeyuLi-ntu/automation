import unittest,copy
from pathlib import Path
from decimal import Decimal
from market_rates.common import load
from market_rates.fx_promo import normalize_fx,promotion_dates
from market_rates.rules import main_offer
from scripts.verify_board_wave import canonical_transcription

ROOT=Path(__file__).resolve().parents[1]
class FxPromotionTests(unittest.TestCase):
    def section(self,bank):
        folders={'ICBC':'i','SCB':'i','CITI':'i','DBS':'i','HSBC':'h','BEA':'d','CIMB':'a','RHB':'c','SBI':'c'}
        return load(ROOT/'runs'/('fx-promo-20260928-'+folders[bank])/bank/'run.json')['sections']
    def test_dbs_derived_not_stale_headline(self):
        board=load(ROOT/'runs/remaining-board-20260928-combined-v2/run.json')['llm']['offers'];r=normalize_fx(self.section('DBS')[0],board)
        self.assertEqual(len(r),10);self.assertEqual(max(Decimal(x['rate_pct']) for x in r),Decimal('4.26'))
        self.assertTrue(all(Decimal(x['amount_min'])>=10000 and Decimal(x['amount_max'])<=500000 for x in r))
        self.assertEqual({x['rate_pct'] for x in r if x['tenor_value']==12},{'3.8','4.1'})
    def test_icbc_currency_and_channel_thresholds(self):
        sections=self.section('ICBC');cny=normalize_fx(sections[0]);usd=normalize_fx(sections[1])
        self.assertEqual((len(cny),len(usd)),(10,10));self.assertTrue(all('20,000' in r['conditions'] for r in cny+usd));self.assertTrue(all(r['channel']=='电子银行/柜台' for r in cny))
        low=[r for r in usd if r['channel']=='电子银行' and r['amount_max']=='5000'];self.assertEqual(len(low),5);self.assertTrue(all(not r['max_inclusive'] for r in low));self.assertEqual(low[2]['rate_pct'],'3.9')
    def test_hsbc_personal_ranking_separate_from_highest(self):
        r=[o for s in self.section('HSBC') for o in normalize_fx(s) if o['currency']=='USD' and o['tenor_value']==3]
        self.assertEqual(main_offer(r)['rate_pct'],'3.75');self.assertEqual(max(Decimal(o['rate_pct']) for o in r),Decimal('4.5'))
        self.assertTrue(all('非App' in o['conditions'] for o in r))
    def test_citi_conversion_equivalent_and_new_funds_distinct(self):
        a,b=self.section('CITI');r=normalize_fx(a);nf=normalize_fx(b)
        self.assertTrue(all(x['amount_min']=='50000' and x['amount_currency']=='USD' and x['amount_is_equivalent'] for x in r));self.assertIn('CNH',{x['currency'] for x in r});self.assertNotIn('JPY',{x['currency'] for x in r})
        self.assertEqual({x['rate_pct'] for x in nf},{'4','4.5'});self.assertTrue(all(x['fresh_funds']=='yes' and x['amount_min']=='5000' for x in nf))
    def test_sbi_aggregate_limit_not_per_placement(self):
        r=normalize_fx(self.section('SBI')[0])[0];self.assertFalse(r['max_inclusive']);self.assertIn('合计',r['conditions']);self.assertEqual(r['amount_min'],'25000')
    def test_validity_moves_with_source_not_collection_date(self):
        s=copy.deepcopy(self.section('CIMB')[0]);self.assertEqual(promotion_dates(s),('2026-09-01','2026-09-30'))
        for e in s['extra_evidence']:e['quote']=e['quote'].replace('September','November')
        self.assertEqual(promotion_dates(s),('2026-11-01','2026-11-30'))
        r=normalize_fx(s);self.assertTrue(all(x['valid_to']=='2026-11-30' for x in r))
    def test_term_typography_does_not_hide_financial_errors(self):
        task={'kind':'text','comparison_profile':'promo-terms'};c=lambda x:canonical_transcription(x,task)
        self.assertEqual(c('3. “Fresh Funds” required.'),c('"Fresh Funds" required'))
        for a,b in [('1.25%','1.35%'),('USD50,000','USD5,000'),('<=5000','<5000'),('not required','required'),('30 days','3 days')]:self.assertNotEqual(c(a),c(b))
    def test_all_active_source_waves_are_checked(self):
        from market_rates.board_wave import validate_wave
        run=load(ROOT/'runs/fx-promo-combined-20260928-a/run.json')
        self.assertEqual(len(run['fx_sources']),9)
        for src in run['fx_sources']:validate_wave(src)
    def test_expired_boc_and_two_month_bundles_remain_outside_active(self):
        run=load(ROOT/'runs/fx-promo-combined-20260928-a/run.json');self.assertFalse(any(x['bank']=='BOC' for x in run['llm']['offers']));self.assertEqual(len(run['deferred']),32)
        self.assertTrue(all(x['offer']['valid_to']=='2026-09-27' for x in run['deferred'] if x['offer']['bank']=='BOC'))
    def test_all_116_quotes_reach_both_outputs(self):
        p=load(ROOT/'outputs/fx-promo-20260928-c/table-validation-plan.json')
        self.assertEqual(sum(r['insertable'] for r in p['details']),116)
        self.assertEqual(sum(len(i['rows']) for h in p['histories'] for i in h['inserts']),116)
        self.assertEqual(sum(len(g['rows']) for b in p['rainbow_blocks'] for g in b['groups']),116)
        self.assertTrue(any(i.get('kind')=='tenor' and i['currency']=='EUR' for h in p['histories'] for i in h['inserts']))

if __name__=='__main__':unittest.main()

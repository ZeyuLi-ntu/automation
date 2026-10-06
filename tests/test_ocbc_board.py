import unittest
from copy import deepcopy
from market_rates.board_wave import normalize_section

class OCBCBoardTests(unittest.TestCase):
    def section(self,cur='USD'):
        head=['Time Deposit Amt']+[str(n)+'- month' for n in [1,2,3,5,6,7,8,9,12]]+['Value Date']
        return dict(id='ocbc-test',bank='OCBC',currency=cur,product_id='ocbc-fx-online-board',layout='ocbc-fx',page_id='rates',
            rows=[head,['First $49,999']+['3.25000','0.0','3.35000','0.0','3.45000','0.0','0.0','3.55000','3.65000']+['30/09/2026']],
            minimum='5000',rate_basis='annual_nominal',valid_from='2026-09-28',basis_evidence=[dict(page_id='terms',quote='original source',locator='minimum')])

    def test_first_amount_uses_product_minimum_and_preserves_zero(self):
        r=normalize_section(self.section(),'llm')
        self.assertEqual(len(r),9);self.assertEqual(r[0]['amount_min'],'5000');self.assertEqual(r[0]['amount_max'],'49999')
        self.assertTrue(r[0]['max_inclusive']);self.assertEqual(r[1]['rate_pct'],'0');self.assertEqual(r[0]['channel'],'online')
        self.assertEqual(r[0]['valid_from'],'2026-09-28');self.assertIn('30/09/2026',r[0]['evidence'][0]['quote'])

    def test_hkd_has_distinct_minimum_and_above_is_exclusive(self):
        s=self.section('HKD');s['minimum']='50000';s['rows'][1][0]='First $499,999'
        r=normalize_section(s,'vlm');self.assertEqual((r[0]['amount_min'],r[0]['amount_max']),('50000','499999'))
        s['rows'][1][0]='Above $5,000,000';r=normalize_section(s,'vlm')
        self.assertEqual(r[0]['amount_min'],'5000000');self.assertFalse(r[0]['min_inclusive']);self.assertIsNone(r[0]['amount_max'])

    def test_malformed_columns_unknown_currency_and_missing_basis_stop(self):
        for alter in [lambda s:s['rows'][1].pop(),lambda s:s.update(currency='JPY'),lambda s:s.update(basis_evidence=[]),lambda s:s.update(minimum=None)]:
            s=self.section();alter(s)
            with self.assertRaises(ValueError):normalize_section(s,'llm')

    def test_sgd_ranges_renewal_na_and_thresholds(self):
        s=self.section('SGD');s.update(layout='ocbc-sgd',product_id='ocbc-sgd-board',rows=[
            ['Tenure (months)','S$5,000 - S$20,000','>S$20,000 - S$50,000','>S$50,000 - S$99,999'],
            ['1 - 2','0.05%','0.05%','0.05%'],['24 (new placements not available*)','1.45%','0.20%','0.20%'],
            ['48 (new placements not available*)','2.20%','0.20%','N.A']])
        r=normalize_section(s,'llm');self.assertEqual(len(r),11)
        self.assertTrue(all('仅同期限旧存款续期' in o['conditions'] for o in r if o['tenor_value']>=24))
        self.assertTrue(all(not o['min_inclusive'] for o in r if o['amount_min']=='20000'))
        self.assertTrue(all('仅同期限旧存款续期' not in o['conditions'] for o in r if o['tenor_value']<24))

if __name__=='__main__':unittest.main()

import unittest
from market_rates.common import load
from market_rates.board_wide_plan import matrix_groups,history_groups
from market_rates.workbook_policy import quote_in_scope
from market_rates.board_cleanup import scb_audience,scb_low_band

class CompactBankLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs=load('runs/board-personal-scope-20260928-a/run.json')['llm']['offers']
    def test_sgd_source_columns_survive_minimum_and_renewal_notes(self):
        for bank,count in [('Maybank',4),('OCBC',6),('RHB',2),('SCB',5)]:
            rs=[dict(r,insertable=not(bank=='RHB' and r['tenor_value'] in [1,2])) for r in self.rs if r['bank']==bank and r['currency']=='SGD']
            groups=matrix_groups(rs)
            self.assertEqual(len(groups),count,bank)
            self.assertEqual(sum(map(len,groups)),sum(r['insertable'] for r in rs),bank)
    def test_maybank_first_band_keeps_all_nine_tenors(self):
        rs=[r for r in self.rs if r['bank']=='Maybank' and r['currency']=='SGD']
        self.assertEqual({r['tenor_value'] for r in matrix_groups(rs)[0]},{1,2,3,6,9,12,18,24,36})
    def test_maybank_ordinary_fx_scope(self):
        rs=[r for r in self.rs if r['bank']=='Maybank' and r['currency']=='USD' and quote_in_scope(r)]
        self.assertEqual({r['product_id'] for r in rs},{'maybank-fx-tier1-board','maybank-fx-tier2-board','maybank-fx-tier3-board'})
    def test_singapura_two_columns_keep_short_and_long_minimums(self):
        rs=[r for r in self.rs if r['bank']=='Singapura Finance' and r['currency']=='SGD']
        groups=matrix_groups(rs)
        self.assertEqual(len(groups),2)
        self.assertEqual(sum(map(len,groups)),len(rs))
        self.assertEqual({r['amount_min'] for r in groups[0]},{'500','5000'})
        self.assertTrue(all(r['amount_max']=='50000' and not r['max_inclusive'] for r in groups[0]))
    def test_scb_low_tiers_merge_only_when_rates_match(self):
        rs=[r for r in self.rs if r['bank']=='SCB' and r['currency']=='USD' and r['tenor_unit']=='M' and r['tenor_value']==6]
        self.assertEqual(len(history_groups(rs)),4)
        changed=[dict(r,rate_pct='3.06') if r['amount_min']=='5000' else r for r in rs]
        self.assertEqual(len(history_groups(changed)),6)
        self.assertTrue(scb_low_band('5,000-99,999'))
        self.assertFalse(scb_low_band('100,000-249,999'))
    def test_scb_audiences_are_distinct(self):
        self.assertEqual(scb_audience('Priority Private Banking (USD 25K)'),'private')
        self.assertEqual(scb_audience('Priority Banking (USD 25K)'),'premier')
        self.assertEqual(scb_audience('外币定存促销 / personal'),'personal')

if __name__=='__main__':unittest.main()

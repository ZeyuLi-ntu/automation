import unittest
from pathlib import Path
from market_rates.common import load
from market_rates.workbook_policy import quote_in_scope
from market_rates.board_wide_plan import matrix_groups
from market_rates.fx_promo import normalize_fx

ROOT=Path(__file__).resolve().parents[1]
class PersonalScopeTests(unittest.TestCase):
    def test_hsbc_policy_is_scoped_not_all_premier_banks(self):
        base=dict(bank='HSBC',currency='USD',rate_type='board',audience='premier')
        self.assertFalse(quote_in_scope(base));self.assertTrue(quote_in_scope(dict(base,audience='personal')))
        self.assertFalse(quote_in_scope(dict(base,rate_type='promo',audience='premier_elite')))
        self.assertTrue(quote_in_scope(dict(base,bank='SCB')))
        self.assertTrue(quote_in_scope(dict(base,rate_type='promo',currency='SGD')))
    def test_hlf_two_columns_do_not_merge_away_tenor_minimums(self):
        offers=load(ROOT/'runs/remaining-board-20260928-combined-v2/run.json')['llm']['offers']
        rs=[r for r in offers if r['bank']=='HLF' and r['currency']=='SGD'];groups=matrix_groups(rs)
        self.assertEqual(len(groups),2);self.assertEqual(sum(map(len,groups)),len(rs))
        low=groups[0]
        self.assertEqual({r['amount_min'] for r in low if r['tenor_value'] in [1,2]},{'10000'})
        self.assertEqual({r['amount_min'] for r in low if r['tenor_value']>=3},{'500'})
        self.assertEqual({r['rate_pct'] for r in low if r['tenor_value']==3},{'0.1'})
    def test_icbc_exactly_two_bands_and_correct_boundaries(self):
        sections=load(ROOT/'runs/fx-promo-20260928-i/ICBC/run.json')['sections']
        for s in sections:
            rs=normalize_fx(s);threshold='50000' if s['currency']=='CNY' else '5000'
            self.assertEqual(len(rs),10)
            for t in [1,3,6,9,12]:
                two=[r for r in rs if r['tenor_value']==t];self.assertEqual(len(two),2)
                self.assertEqual((two[0]['amount_min'],two[0]['amount_max'],two[0]['max_inclusive']),('500',threshold,False))
                self.assertEqual((two[1]['amount_min'],two[1]['amount_max'],two[1]['min_inclusive']),(threshold,None,True))
    def test_hsbc_personal_rates_match_user_table(self):
        wave=load(ROOT/'runs/fx-promo-20260928-h/HSBC/run.json')
        rs=[r for s in wave['sections'] for r in normalize_fx(s) if r['currency']=='USD' and quote_in_scope(r)]
        self.assertEqual({r['tenor_value']:r['rate_pct'] for r in rs},{3:'3.75',6:'2.9',12:'2.75'})
        self.assertEqual(len(rs),3)

if __name__=='__main__':unittest.main()

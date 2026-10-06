import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from market_rates.amount_rows import same_amount
from market_rates.board_cleanup import plan
from market_rates.common import load
from market_rates.fx_promo import normalize_fx,promotion_dates

ROOT=Path(__file__).resolve().parents[1]
class RowAndBocFixTests(unittest.TestCase):
    def test_cimb_old_range_minimum_and_quote_point_match(self):
        a='10k-50k'
        self.assertTrue(same_amount(a,'定期存款挂牌；USD ≥10,000；personal','CIMB'))
        self.assertTrue(same_amount(a,'定期存款挂牌；USD ≥10,000 且≤10,000；personal','CIMB'))
        self.assertFalse(same_amount(a,'USD ≥50,000','CIMB'))
        self.assertFalse(same_amount('USD ≥10,000','SGD ≥10,000','CIMB'))
    def test_other_bank_upper_band_matches_only_unambiguous(self):
        b='挂牌；USD ≥10,000 且≤24,999；personal'
        self.assertTrue(same_amount('25,000以下',b,'DBS',[b]))
        self.assertFalse(same_amount('25,000以下',b,'DBS',[b,'USD ≥5,000 且≤24,999']))
    def fixture(self):
        return {'USD挂牌':{'B2':'Tenor: 1 month','B4':'CIMB','C4':'10k-50k','D4':'-','E4':'0.027','C5':'USD ≥10,000','D5':'-','E5':'-','C6':'USD ≥10,000 且≤10,000','D6':'0.0285','E6':'-','H3':'当日增幅'},
                'CNY挂牌':{'A2':'Tenor: 1 month','A4':'Maybank','B4':'CNY ≥1000','C4':'0.01','D4':'0.01','B5':'挂牌；CNY ≥1000；personal','C5':'0.02','D5':'0.02','H3':'当日增幅'},
                'SGD挂牌':{'A3':'CIMB','B3':'lower','D3':'0.002','F3':'-','B4':'higher','F4':'0.0035','B5':'lower long','F5':'0.003','A9':'Next Bank','D9':'0.099'}}
    def test_history_preserved_conflict_kept_and_sgd_transfer(self):
        v=self.fixture();f=copy.deepcopy(v);f['USD挂牌']['D6']="='挂牌明细'!I4"
        merges={'USD挂牌':['B4:B6'],'CNY挂牌':['A4:A5'],'SGD挂牌':['A3:A8']}
        with tempfile.TemporaryDirectory() as tmp,patch('market_rates.board_cleanup.read_xlsx',side_effect=[v,f]),patch('market_rates.board_cleanup.merged_ranges',return_value=merges):
            p=plan('unused.xlsx',tmp)
        usd,cny=p['sheets'];self.assertEqual(usd['delete_rows'],[5,6]);self.assertEqual(cny['delete_rows'],[]);self.assertEqual(len(cny['conflicts']),1)
        updates={u['final_address']:u for u in usd['updates']}
        self.assertEqual(updates['D4']['expected'],.0285);self.assertEqual(updates['E4']['expected'],.027)
        self.assertEqual(updates['D4']['value'],"='挂牌明细'!I4")
        self.assertEqual(next(x for x in p['cimb_sgd']['updates'] if x['address']=='F3')['expected'],.003)
        self.assertEqual(p['cimb_sgd']['delete_rows'],[5,6,7,8])
    def test_already_two_sgd_rows_does_not_read_next_bank(self):
        v=self.fixture();v['SGD挂牌']['A5']='Other';v['SGD挂牌']['D5']='0.099'
        merges={'USD挂牌':['B4:B6'],'CNY挂牌':['A4:A5'],'SGD挂牌':['A3:A4']}
        with tempfile.TemporaryDirectory() as tmp,patch('market_rates.board_cleanup.read_xlsx',return_value=v),patch('market_rates.board_cleanup.merged_ranges',return_value=merges):p=plan('unused.xlsx',tmp)
        self.assertEqual(p['cimb_sgd']['delete_rows'],[])
        self.assertEqual(next(x for x in p['cimb_sgd']['updates'] if x['address']=='D3')['expected'],.002)
    def test_boc_six_currencies_and_actual_expiry(self):
        s=load(ROOT/'runs/fx-promo-20260928-b/BOC/run.json')['sections'][0]
        rs=normalize_fx(s)
        self.assertEqual(len(rs),28);self.assertEqual({r['currency'] for r in rs},{'USD','CNY','AUD','NZD','EUR','GBP'})
        self.assertEqual(promotion_dates(s),('2026-09-21','2026-09-27'))
        self.assertTrue(all(r['product_id']=='boc-fx-mobile' and r['valid_to']=='2026-09-27' for r in rs))
        self.assertEqual({r['rate_pct'] for r in rs if r['currency']=='USD' and r['tenor_value']==6},{'4.1','4.3'})
        self.assertEqual({r['rate_pct'] for r in rs if r['currency']=='AUD'},{'4','4.35'})

if __name__=='__main__':unittest.main()

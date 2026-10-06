from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from market_rates.demo import offer
from market_rates.schema import normalize,group_key
from market_rates.rules import build_views
from market_rates.manual_review import items,record,effective_offers,add_offer,EDITABLE,catalog
from market_rates.common import digest
from market_rates.scope import currency_code
from market_rates.board_extractor import number,tenor,rate,literal_date
from market_rates.board_plan import amount,cell_number
from market_rates.workbook_policy import bank_in_scope

class MultiCurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.rows=[]
        for curr,typ,n in [('SGD','promo','1.1'),('SGD','board','1.2'),('USD','board','3.2')]:
            r=offer('HLB','same-product',rate=n);r.update(currency=curr,amount_currency=curr,rate_type=typ);self.rows.append(normalize(r))
        self.run=dict(id='multicurrency-test',as_of='2026-09-27',evidence_hash='fixture-only',pages=[],bank_dates={'HLB':'2026-09-27'},llm={'offers':self.rows},vlm={'offers':deepcopy(self.rows)},manual_catalog=[dict(bank='HLB',currency=c,amount_currency=c,rate_type='board',product_id='same-product') for c in ['SGD','USD']])
    def tearDown(self):self.temp.cleanup()
    def test_currencies_categories_and_ledger_never_mix(self):
        self.assertEqual(len({group_key(r) for r in self.rows}),3)
        cfg={'rate_scopes':[{'currency':c,'rate_type':'board'} for c in ['SGD','USD']]}
        views=build_views(self.rows,cfg,{},'2026-09-27');self.assertEqual(len(views['groups']),2);self.assertEqual(set(views['order']),{'SGD/board/6M','USD/board/6M'})
        item=next(i for i in items(self.run,self.root) if i['original']['currency']=='USD')
        record(self.run,dict(version=0,id=item['id'],fingerprint=item['fingerprint'],action='replace',fields={'rate_pct':'3.3'},author='synthetic test',reason='isolation regression',persist=True),self.root)
        out,bad,_=effective_offers(self.run,self.root);self.assertFalse(bad);self.assertEqual({(r['currency'],r['rate_type']):r['rate_pct'] for r in out},{('SGD','promo'):'1.1',('SGD','board'):'1.2',('USD','board'):'3.3'})
    def test_ambiguous_add_requires_currency_selection(self):
        r=deepcopy(self.rows[-1]);r['tenor_value']=9
        d=dict(version=0,bank='HLB',fields={k:r[k] for k in EDITABLE},author='synthetic test',reason='new tenor fixture',source_url='https://bank.example/fixture',source_quote='synthetic fixture')
        with self.assertRaises(ValueError):add_offer(self.run,d,self.root)
        d['catalog_id']=digest(catalog(self.run)[1]);result=add_offer(self.run,d,self.root)
        self.assertEqual(result['offer']['currency'],'USD');self.assertEqual(result['offer']['amount_currency'],'USD')
    def test_unknown_and_ranges_never_become_false_single_tenors(self):
        self.assertIsNone(tenor('8days-<1 month (as above)'));self.assertIsNone(tenor('Above 24 months to 60 months'))
        self.assertIsNone(rate(None));self.assertEqual(rate('Nil'),'0');self.assertEqual(rate('3.185500'),'3.1855')
        self.assertEqual(number('< 1 mio'),'1000000');self.assertEqual(literal_date('25-Sep-2026 9:20AM'),'2026-09-25')
        self.assertEqual(cell_number('3.1855E-2'),.031855)
    def test_alias_and_amount_currency(self):
        self.assertEqual(currency_code('rmb'),'CNY');self.assertEqual(currency_code('CNH'),'CNH')
        self.assertFalse(bank_in_scope('TrustBank'));self.assertFalse(bank_in_scope('MariBank'))
        r=deepcopy(self.rows[-1]);r.update(amount_min='5000',amount_max='1000000',max_inclusive=False)
        self.assertIn('USD',amount(r));self.assertIn('<1,000,000',amount(r))

if __name__=='__main__':unittest.main()

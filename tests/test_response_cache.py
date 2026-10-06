from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile,unittest
from market_rates import response_cache as cache
from market_rates.common import save,load
from market_rates.schema import financial_terms
from market_rates.demo import offer
from market_rates.manual_review import effective_offers
from market_rates.workbook_policy import bank_in_scope

class ResponseCacheTests(unittest.TestCase):
    def test_key_changes_for_text_image_model_rules_and_lane(self):
        args=[{'text':'2.00','image':'abc'},{'model_digest':'m1'},'r1','llm']
        original=cache.cache_key(*args)
        for index,value in [(0,{'text':'2.01','image':'abc'}),(0,{'text':'2.00','image':'def'}),(1,{'model_digest':'m2'}),(2,'r2'),(3,'vlm')]:
            changed=deepcopy(args);changed[index]=value;self.assertNotEqual(original,cache.cache_key(*changed))
    def test_age_and_tamper_force_new_extraction(self):
        response={'done':True,'done_reason':'stop','message':{'content':'{}'}}
        with tempfile.TemporaryDirectory() as tmp:
            cache.write(tmp,'key',response);self.assertEqual(cache.read(tmp,'key'),response)
            record=load(Path(tmp)/'key.json');future=datetime.fromisoformat(record['created_at'])+timedelta(days=28)
            self.assertIsNone(cache.read(tmp,'key',now=future))
            record['response']['message']['content']='changed';save(Path(tmp)/'key.json',record)
            self.assertIsNone(cache.read(tmp,'key'))
    def test_effective_rate_disagreement_blocks_bundle(self):
        row=offer('Maybank','maybank-sgd-bundle',rate='2')
        row['conditions']='组合有效年利率：1.82%；附加存款比例：10%'
        other=deepcopy(row);other['conditions']='组合有效年利率：1.92%；附加存款比例：10%'
        with tempfile.TemporaryDirectory() as tmp:
            run=dict(id='test',as_of='2026-09-27',pages=[],llm={'offers':[row]},vlm={'offers':[other]})
            good,bad,_=effective_offers(run,tmp);self.assertFalse(good);self.assertTrue(bad)
        self.assertEqual(financial_terms(row),('1.82','10'))
    def test_bank_exclusions_include_aliases(self):
        for b in ['MARI','Maribank','MariBank','TRUST','Trust']:self.assertFalse(bank_in_scope(b))
        self.assertTrue(bank_in_scope('Maybank'))

if __name__=='__main__':unittest.main()

from pathlib import Path
import unittest
from market_rates.common import load
from market_rates.multi_bank_validation import raw_matched_offers
from market_rates.workbook_policy import workbook_policy

ROOT=Path(__file__).resolve().parents[1]

class RemainingBankTests(unittest.TestCase):
    def test_citi_investment_2m_is_detail_only(self):
        p=workbook_policy()
        for segment in ['gold','private']:
            self.assertIn('CITI/citi-'+segment+'-investment-bundle/2M',p['deferred_actual_tenors'])

    @unittest.skipUnless((ROOT/'runs/remaining-HSBC-20260927-v2/run.json').exists(),'Frozen local evidence not installed')
    def test_frozen_new_banks_have_no_missing_or_differing_tiers(self):
        samples={'BEA':('v2',2),'HSBC':('v2',16),'SingFinance':('v3',12),'Singapura-Finance':('v3',8),'CITI':('v6',6)}
        for b,(v,count) in samples.items():
            run=load(ROOT/f'runs/remaining-{b}-20260927-{v}/run.json');rows,bad=raw_matched_offers(run)
            self.assertEqual(bad,[]);self.assertEqual(len(rows),count)
            if b=='HSBC':self.assertEqual({r['tenor_value']:r['rate_pct'] for r in rows if r['audience']=='personal'},{3:'1.6',6:'1.8',9:'0.9',12:'0.95'})
            if b=='SingFinance':
                self.assertEqual(sorted((r['amount_min'],r['rate_pct']) for r in rows if r['tenor_value']==6),[('1000','1.5'),('10000','1.8')])

if __name__=='__main__':unittest.main()

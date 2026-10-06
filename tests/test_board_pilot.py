from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from market_rates.common import load
from market_rates.board_plan import make_plan,ROOT
from market_rates.manual_review import items,record

class BoardPilotTests(unittest.TestCase):
    def test_percent_policy_historical_mapping_and_manual_currency_isolation(self):
        runpath=ROOT/'runs/board-pilot-20260927-a'
        if not runpath.exists():self.skipTest('Local captured fixture not installed')
        run=load(runpath/'run.json')
        # The pilot predates the wide layout. Pin its captured template instead
        # of following a mutable pointer to the newest production workbook.
        base_path=ROOT/'outputs/maybank-bundle-scope-20260927-200235/table-validation-plan.json'
        if not base_path.exists():self.skipTest('Captured pilot template not installed')
        base=load(base_path)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            from market_rates.manual_review import effective_offers
            def local(r):return effective_offers(r,root)
            with patch('market_rates.board_plan.effective_offers',side_effect=local):
                before=make_plan(runpath,root/'before',base=base)
                self.assertEqual(sum(r['insertable'] for r in before['details']),27)
                self.assertTrue(any(x['formula'].startswith('=') for x in before['usd_rows'] if x['bank']=='SBI'))
                self.assertEqual(next(m for m in before['matrix'] if m['bank']=='SBI')['cells'][-1]['formula'],'-')
                item=next(i for i in items(run,root) if i['bank']=='HLB' and i['original']['currency']=='USD' and i['original']['tenor_value']==1)
                record(run,dict(version=0,id=item['id'],fingerprint=item['fingerprint'],action='replace',fields={'rate_pct':'3.3'},author='test fixture',reason='synthetic USD-only revision',persist=True),root)
                after=make_plan(runpath,root/'after',base=base)
                self.assertEqual(before['matrix'],after['matrix'])
                self.assertEqual(next(r for r in after['usd_rows'] if r['bank']=='HLB' and r['tenor']=='1M')['expected'],.033)
                self.assertEqual([b for b in before['rainbow_blocks'] if b['currency']=='SGD'],[b for b in after['rainbow_blocks'] if b['currency']=='SGD'])
    def test_new_disagreement_blocks_numeric_draft(self):
        runpath=ROOT/'runs/board-pilot-20260927-a'
        if not runpath.exists():self.skipTest('Local captured fixture not installed')
        with tempfile.TemporaryDirectory() as t,patch('market_rates.board_plan.effective_offers',return_value=([],['conflicting-product'],[])):
            with self.assertRaisesRegex(ValueError,'core disagreements'):make_plan(runpath,Path(t)/'must-not-exist')
            self.assertFalse((Path(t)/'must-not-exist').exists())

if __name__=='__main__':unittest.main()

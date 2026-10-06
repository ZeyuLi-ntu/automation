from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from market_rates.demo import offer
from market_rates.manual_review import items,record,effective_offers,ledger,add_offer,EDITABLE

class ManualReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        row=offer('A','a-promo',rate='1.7')
        self.run=dict(id='test',as_of='2026-09-27',evidence_hash='test',pages=[],llm=dict(offers=[row]),vlm=dict(offers=[deepcopy(row)]))
    def tearDown(self):self.temp.cleanup()
    def save(self,**kwargs):
        i=items(self.run,self.root)[0]
        doc=dict(version=ledger(self.root)['version'],id=i['id'],fingerprint=i['fingerprint'],action='replace',fields={'rate_pct':'1.9'},author='test',reason='synthetic regression',persist=True)
        doc.update(kwargs);return record(self.run,doc,self.root)
    def test_saved_revision_preserves_raw_and_applies_to_both_workbooks_source(self):
        original=deepcopy(self.run);self.save()
        rows,bad,receipts=effective_offers(self.run,self.root)
        self.assertEqual(rows[0]['rate_pct'],'1.9');self.assertEqual(bad,[]);self.assertEqual(self.run,original);self.assertEqual(len(receipts),1)
    def test_new_period_carries_price_but_does_not_approve_new_disagreement(self):
        self.save();self.run['id']='next'
        for lane in ['llm','vlm']:self.run[lane]['offers'][0]['rate_pct']='1.6'
        rows,_,receipts=effective_offers(self.run,self.root)
        self.assertEqual(rows[0]['rate_pct'],'1.9');self.assertTrue(receipts[0]['carried_forward'])
        self.run['vlm']['offers'][0]['rate_pct']='1.5'
        self.assertTrue(effective_offers(self.run,self.root)[1]);self.assertEqual(effective_offers(self.run,self.root)[0],[])
    def test_eligibility_change_never_inherits_old_override(self):
        self.save()
        for lane in ['llm','vlm']:self.run[lane]['offers'][0]['amount_min']='9999'
        self.assertEqual(effective_offers(self.run,self.root)[0][0]['rate_pct'],'1.7')
    def test_disagreement_requires_explicit_selection(self):
        self.run['vlm']['offers'][0]['rate_pct']='1.5'
        with self.assertRaisesRegex(ValueError,'分歧'):self.save(action='confirm')
        self.save(action='vlm');self.assertEqual(effective_offers(self.run,self.root)[0][0]['rate_pct'],'1.5')
    def test_reset_revokes_carry_without_deleting_audit(self):
        self.save();self.save(action='reset',persist=False)
        self.assertEqual(effective_offers(self.run,self.root)[0][0]['rate_pct'],'1.7');self.assertEqual(len(ledger(self.root)['revisions']),2)
    def test_stale_version_and_non_price_persistence_rejected(self):
        self.save()
        with self.assertRaisesRegex(ValueError,'其他窗口'):self.save(version=0)
        with self.assertRaisesRegex(ValueError,'仅适用于本次'):self.save(fields={'amount_min':'9999'})
    def test_excluding_one_tier_does_not_leave_a_false_conflict(self):
        self.run['vlm']['offers'][0]['rate_pct']='1.5';self.save(action='exclude',persist=False)
        rows,bad,_=effective_offers(self.run,self.root);self.assertEqual(rows,[]);self.assertEqual(bad,[])

    def test_changed_validity_requires_fresh_review_of_persistent_price(self):
        self.save()
        for lane in ['llm','vlm']:self.run[lane]['offers'][0]['valid_to']='2026-12-31'
        self.assertEqual(effective_offers(self.run,self.root)[0][0]['rate_pct'],'1.7')

    def test_manual_addition_has_source_audit_dedup_and_one_period_scope(self):
        self.run['coverage']=[dict(bank='Maybank',numeric_insertion=False)]
        row=offer('Maybank','maybank-sgd-promo',rate='1.1')
        doc=dict(version=0,bank='Maybank',fields={k:row[k] for k in EDITABLE},author='synthetic test',
            reason='missing offer',source_url='https://bank.example/rates',source_quote='synthetic fixture, not a real quote')
        before=deepcopy(self.run);r=add_offer(self.run,doc,self.root)
        self.assertEqual(self.run,before);self.assertEqual(len(effective_offers(self.run,self.root)[0]),2)
        doc['version']=1
        with self.assertRaisesRegex(ValueError,'已存在'):add_offer(self.run,doc,self.root)
        revision=dict(version=1,id=r['id'],fingerprint=r['fingerprint'],action='replace',fields={'rate_pct':'1.2'},author='test',reason='fixture',persist=True)
        with self.assertRaisesRegex(ValueError,'仅适用于本次'):record(self.run,revision,self.root)
        revision['persist']=False;record(self.run,revision,self.root)
        self.assertEqual(ledger(self.root)['revisions'][-1]['source_url'],doc['source_url'])
        self.run['as_of']='2026-10-04'
        self.assertEqual(len(effective_offers(self.run,self.root)[0]),1)

if __name__=='__main__':unittest.main()

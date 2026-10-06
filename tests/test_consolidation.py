from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from market_rates.common import save,digest
from market_rates.demo import offer
from market_rates.consolidate import qualify,consolidate

class ConsolidationTests(unittest.TestCase):
    def fixture(self,path,banks=None):
        row=offer('A','a');page=dict(id='A',bank='A',ok=True,complete=True,image_hashes={})
        run=dict(as_of='2026-09-26',pages=[page],evidence_hash=digest([page]),llm=dict(offers=[row],coverage_complete=True),vlm=dict(offers=[deepcopy(row)],coverage_complete=True))
        save(path/'run.json',run);save(path/'config.snapshot.json',dict(expected_banks=banks or ['A']))
        return run

    def test_live_agreement_is_not_labelled_an_independent_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            result=qualify(root,allow_agreement=True)
            self.assertEqual(result['kind'],'dual_agreement_only')
            self.assertFalse((root/'benchmark.json').exists())

    def test_missing_bank_prevents_partial_batch_from_looking_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root,['A','B'])
            with self.assertRaisesRegex(ValueError,'覆盖不足'):qualify(root,True)

    def test_numeric_disagreement_is_not_bypassed_by_live_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=self.fixture(root);run['vlm']['offers'][0]['rate_pct']='9'
            save(root/'run.json',run)
            with self.assertRaises(ValueError):qualify(root,True)

    def test_frozen_mode_requires_a_pinned_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            with self.assertRaisesRegex(ValueError,'缺少对应本次证据'):qualify(root)

    def test_partial_attachment_failure_blocks_even_with_matching_rates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=self.fixture(root);run['errors']=['A https://bank.example/terms.pdf: PDF HTTP 404']
            save(root/'run.json',run)
            with self.assertRaisesRegex(ValueError,'采集失败'):qualify(root,True)

if __name__=='__main__':unittest.main()

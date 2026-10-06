"""A bank failure must remain visible without blocking an authorized subset."""
import tempfile
import unittest
from pathlib import Path
from market_rates.common import save, load, digest
from scripts.qualify_board_wave import qualify


class QualifiedSubsetTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source'
        source.mkdir()
        tasks = [dict(id=k, kind='grid', expected=[['3 month', '0.50% p.a.']], images=[]) for k in ['ok', 'bad']]
        run = dict(id='source', tasks=tasks, task_hash=digest(tasks), sections=[
            dict(id=k, bank=bank, currency='SGD', product_id=k, task_ids=[k])
            for k, bank in [('ok', 'DBS'), ('bad', 'UOB')]
        ], errors=[dict(bank='BEA', source='BEA-D9', error='source unavailable')])
        proof = dict(task_hash=run['task_hash'], passed=False, checks=[
            dict(task=t['id'], lane=lane, passed=(t['id']=='ok' or lane=='llm'), task_hash=digest(t))
            for t in tasks for lane in ['llm', 'vlm']
        ])
        save(source / 'run.json', run)
        save(source / 'wave-checks.json', proof)
        return source, run, proof

    def test_only_complete_sections_and_preserve_capture_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, run, proof = self.fixture(root)
            qualify(source, root / 'qualified')
            result = load(root / 'qualified/run.json')
            self.assertEqual([s['id'] for s in result['sections']], ['ok'])
            self.assertEqual([t['id'] for t in result['tasks']], ['ok'])
            self.assertEqual({c['bank'] for c in result['coverage']}, {'UOB', 'BEA'})
            self.assertEqual(result['qualification_capture_errors'], run['errors'])
            self.assertEqual(result['errors'], [])
            self.assertEqual(load(source / 'run.json'), run)
            self.assertEqual(load(root / 'qualified/full-attempt-checks.json'), proof)

    def test_no_complete_section_never_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _, proof = self.fixture(root)
            for check in proof['checks']:
                check['passed'] = False
            save(source / 'wave-checks.json', proof)
            with self.assertRaisesRegex(ValueError, 'No complete'):
                qualify(source, root / 'qualified')
            self.assertFalse((root / 'qualified').exists())

    def test_proof_from_another_capture_never_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _, proof = self.fixture(root)
            proof['task_hash'] = 'other-capture'
            save(source / 'wave-checks.json', proof)
            with self.assertRaisesRegex(ValueError, 'Proof/source mismatch'):
                qualify(source, root / 'qualified')
            self.assertFalse((root / 'qualified').exists())

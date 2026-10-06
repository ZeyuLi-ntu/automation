import tempfile
import unittest
from pathlib import Path
from market_rates.common import load
from market_rates.board_wide_plan import plan
from market_rates.multi_bank_validation import raw_matched_offers

ROOT=Path(__file__).resolve().parents[1]
BOARD=ROOT/'runs/all-20260930-094412-950659/board/combined'


class BocMaybankCorrectionTests(unittest.TestCase):
    @unittest.skipUnless((BOARD/'run.json').exists(),'Local frozen full batch is not installed')
    def test_old_boc_notice_updates_every_board_display_with_references(self):
        base=load(ROOT/'outputs/board-wide-20260930-110231-926023/table-validation-plan.json')
        with tempfile.TemporaryDirectory() as tmp:
            p=plan(BOARD,Path(tmp)/'plan',base)
        boc=[d for d in p['details'] if d['bank']=='BOC']
        self.assertEqual(len(boc),227)
        self.assertTrue(all(d['insertable'] for d in boc))
        self.assertEqual({d['valid_from'] for d in boc},{'2026-06-22'})
        for matrix in p['matrices']:
            groups=[g for g in matrix['groups'] if g['bank']=='BOC']
            self.assertEqual(len(groups),1)
            self.assertTrue(groups[0]['updated'])
            values=[c for r in groups[0]['rows'] for c in r['values'] if isinstance(c['expected'],(int,float))]
            self.assertTrue(values)
            self.assertTrue(all(p['input_sheet'] in c['formula'] for c in values))
        for h in p['histories']:
            values=[c for c in h['existing'] if c['bank']=='BOC']
            values += [r for ins in h['inserts'] if ins['bank']=='BOC' for r in ins['rows']]
            numbers=[c for c in values if isinstance(c['expected'],(int,float))]
            self.assertTrue(numbers)
            self.assertTrue(all(p['input_sheet'] in c['formula'] for c in numbers))

    @unittest.skipUnless((ROOT/'runs/maybank-standalone-20261001/run.json').exists(),'Local capture is not installed')
    def test_independent_lanes_agree_on_selected_standalone_table(self):
        run=load(ROOT/'runs/maybank-standalone-20261001/run.json')
        rows,bad=raw_matched_offers(run)
        self.assertEqual(bad,[])
        self.assertEqual({r['tenor_value']:r['rate_pct'] for r in rows},{6:'1.85',9:'1.8',12:'1.85'})
        self.assertTrue(all(r['amount_min']=='20000' and r['product_id']=='maybank-sgd-standalone' for r in rows))
        self.assertTrue(all('Deposits Bundle Promotion' not in p['text'] for p in run['pages']))


if __name__=='__main__':unittest.main()

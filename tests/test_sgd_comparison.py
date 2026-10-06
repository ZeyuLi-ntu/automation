import unittest
from market_rates.sgd_comparison import comparisons

class SGDComparisonTests(unittest.TestCase):
    def test_skip_empty_history_without_backfill_and_take_group_max(self):
        sheet={'H1':'当日最高报价变动','A2':'Singapura Finance','C2':'0.017','C3':'0.017','D2':'-','E2':'0.0165','F2':'0.0162'}
        r=comparisons(sheet,['A2:A3'])[0]
        self.assertEqual(r['previous_column'],5)
        self.assertAlmostEqual(r['expected'],.0005)
        self.assertEqual(sheet['D2'],'-')
    def test_missing_and_zero_are_distinct(self):
        sheet={'H1':'当日最高报价变动','A2':'UOB','C2':'0.017'}
        self.assertEqual(comparisons(sheet,[])[0]['expected'],'无上期数据')
        sheet['E2']='0'
        self.assertAlmostEqual(comparisons(sheet,[])[0]['expected'],.017)
    def test_missing_current_not_backfilled(self):
        sheet={'H1':'当日最高报价变动','A2':'UOB','C2':'-','D2':'0.017'}
        self.assertEqual(comparisons(sheet,[])[0]['expected'],'-')

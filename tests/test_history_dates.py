import unittest
from unittest.mock import patch
from market_rates.history_dates import check_dates

class HistoricalDateTests(unittest.TestCase):
    def book(self, dates):
        out={}
        for name,bank,first in [('SGD促销','A',3),('USD挂牌','B',4),('CNY挂牌','A',3),('USD促销','B',4),('CNY促销','A',3)]:
            out[name]={bank+'3':'银行',**{chr(64+first+i)+'3':str(date) for i,date in enumerate(dates)}}
        return out

    def test_partial_template_cannot_drop_a_date(self):
        with patch('market_rates.history_dates.read_xlsx',side_effect=[self.book([46293,46292,46281]),self.book([46293,46281])]):
            with self.assertRaisesRegex(ValueError,'丢失历史日期'):check_dates('previous','partial')

    def test_new_current_date_preserves_old_columns(self):
        with patch('market_rates.history_dates.read_xlsx',side_effect=[self.book([46293,46292]),self.book([46294,46293,46292])]):
            self.assertEqual(check_dates('previous','next')['USD挂牌']['preserved'],2)

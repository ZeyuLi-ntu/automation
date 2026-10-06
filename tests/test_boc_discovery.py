import unittest
from market_rates.boc_discovery import latest_promotion_url,latest_board_announcement


class BocDiscoveryTests(unittest.TestCase):
    def test_board_latest_old_notice_is_still_selected(self):
        links=[dict(text='个人定期存款挂牌利率（２０２６０６２２）',url='https://www.bankofchina.com/june'),
               dict(text='个人定期存款挂牌利率(20260501)',url='https://www.bankofchina.com/may'),
               dict(text='个人定期存款挂牌利率(20261002)',url='https://www.bankofchina.com/future'),
               dict(text='个人定期存款挂牌利率(20261001)',url='https://example.com/wrong')]
        for today in ['20260930','20261001']:
            selected,candidates=latest_board_announcement(links,today)
            self.assertEqual(selected['url'],links[0]['url'])
            self.assertEqual(len(candidates),2)

    def test_pilot_board_quotes_are_write_targets_even_when_unchanged(self):
        from market_rates.board_wide_plan import collected_pairs
        details=[dict(bank=bank,display_currency=cur,valid_from='2026-06-22',date_status='unchanged_date')
                 for bank in ['BOC','HLB','SBI','UOB'] for cur in ['SGD','USD','CNY']]
        pairs=collected_pairs(details)
        self.assertEqual(len(pairs),12)
        self.assertTrue({('BOC','SGD'),('BOC','USD'),('BOC','CNY')}.issubset(pairs))

    def test_printed_grouping_space_preserves_amount(self):
        from market_rates.scb_extractor import parse_money
        self.assertEqual(parse_money('20, 000'),'20000')
        self.assertEqual(parse_money('200, 000'),'200000')
        for value in ['20, 00','20 000','20, 000 200, 000']:
            with self.assertRaises(ValueError):parse_money(value)

    def test_mixed_bracket_latest_title_is_not_skipped(self):
        links=[dict(text='个人定期存款促销利率(20260921)',url='https://www.bankofchina.com/old'),
               dict(text='个人定期存款促销利率(20260928）',url='https://www.bankofchina.com/new')]
        self.assertEqual(latest_promotion_url(links,'20260929'),links[1]['url'])

    def test_spaces_full_width_and_future_dates(self):
        links=[dict(text='个人定期存款促销利率 （２０２６０９２８） ',url='https://www.bankofchina.com/current'),
               dict(text='个人定期存款促销利率(20261005)',url='https://www.bankofchina.com/future'),
               dict(text='个人定期存款促销利率(20260929)',url='https://example.com/untrusted')]
        self.assertEqual(latest_promotion_url(links,'20260929'),links[0]['url'])

    def test_old_latest_publication_remains_eligible(self):
        links=[dict(text='个人定期存款促销利率(20260921)',url='https://www.bankofchina.com/old')]
        self.assertEqual(latest_promotion_url(links,'20260929'),links[0]['url'])

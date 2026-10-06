from copy import deepcopy
import unittest
from market_rates.demo import offer
from market_rates.rules import active, build_views
from market_rates.workbook_policy import promo_reference_allowed


class LatestPromoReferenceTests(unittest.TestCase):
    policy={'promo_quote_date_policy':'latest_published_reference'}

    def row(self):
        return dict(offer('BOC','boc-sgd-mobile'),valid_from='2026-09-21',valid_to='2026-09-27')

    def test_expired_latest_is_presented_without_changing_source_dates(self):
        source=self.row();before=deepcopy(source)
        row=dict(source,reference_quote=promo_reference_allowed(source,'2026-09-29',self.policy))
        self.assertFalse(active(row,'2026-09-29'))
        self.assertFalse(build_views([row],{}, {},'2026-09-29')['groups'])
        groups=build_views([row],{}, {},'2026-09-29',include_reference_quotes=True)['groups']
        self.assertEqual(groups[0]['main_pct'],'1.7')
        self.assertEqual(groups[0]['details'][0]['valid_to'],'2026-09-27')
        self.assertEqual(source,before)

    def test_unchanged_publication_can_be_written_on_repeated_runs(self):
        for day in ['2026-09-29','2026-09-30']:
            self.assertTrue(promo_reference_allowed(self.row(),day,self.policy))

    def test_withdrawn_missing_numeric_future_and_boards_are_not_references(self):
        for changes in [dict(availability='withdrawn'),dict(rate_pct=None),
                        dict(valid_from='2026-10-01'),dict(rate_type='board')]:
            self.assertFalse(promo_reference_allowed(dict(self.row(),**changes),'2026-09-29',self.policy))

    def test_other_banks_and_fx_use_same_policy(self):
        for bank,cur in [('BOC','USD'),('RHB','SGD')]:
            self.assertTrue(promo_reference_allowed(dict(self.row(),bank=bank,currency=cur),'2026-09-29',self.policy))

    def test_still_effective_or_undated_is_normal_quote(self):
        for changes in [dict(valid_to='2026-09-30'),dict(valid_from=None,valid_to=None)]:
            row=dict(self.row(),**changes)
            self.assertTrue(active(row,'2026-09-29'))
            self.assertFalse(promo_reference_allowed(row,'2026-09-29',self.policy))


if __name__=='__main__':unittest.main()

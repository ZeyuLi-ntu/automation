import unittest
from market_rates.fx_promo_plan import publication_notice

class PublicationNoticeTests(unittest.TestCase):
    def test_active_announcement_is_not_expired(self):
        note=publication_notice(dict(valid_from='2026-09-28',valid_to='2026-10-04'),'2026-09-30')
        self.assertNotIn('已截止',note)
        self.assertIn('2026-09-28–2026-10-04',note)

    def test_expired_latest_reference_retains_dates(self):
        note=publication_notice(dict(valid_from='2026-09-21',valid_to='2026-09-27'),'2026-09-30')
        self.assertIn('公告已截止',note)
        self.assertIn('2026-09-21–2026-09-27',note)

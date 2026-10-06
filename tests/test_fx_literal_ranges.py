import unittest
from scripts.verify_board_wave import canonical_transcription

class LiteralRangeTests(unittest.TestCase):
    def test_currency_range_dash_typography(self):
        task={'kind':'grid'}
        a=[['USD / US$5,000 – US$5,000,000','4.00%','4.50%']]
        b=[['USD / US$5,000 - US$5,000,000','4.00%','4.50%']]
        self.assertEqual(canonical_transcription(a,task),canonical_transcription(b,task))
        b[0][0]='USD / US$50,000 - US$5,000,000'
        self.assertNotEqual(canonical_transcription(a,task),canonical_transcription(b,task))

    def test_negative_rate_is_not_missing(self):
        task={'kind':'grid'}
        self.assertNotEqual(canonical_transcription([['-0.05%']],task),canonical_transcription([['0.05%']],task))
        self.assertNotEqual(canonical_transcription([['-0.05%']],task),canonical_transcription([['-']],task))

if __name__=='__main__':unittest.main()

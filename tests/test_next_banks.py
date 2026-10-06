from copy import deepcopy
import unittest
from market_rates.demo import offer
from market_rates.multi_bank_extractor import bind_primary_terms,parse_money,bound

class NextBankTests(unittest.TestCase):
    def term(self,pid,page,text):return dict(product_id=pid,page_id=page,locator=page+'.png',text=text)

    def test_hlb_dates_are_channel_scoped_and_gift_excluded(self):
        pid='hlb-sgd-promo';online=offer('HLB',pid);online.update(channel='online',valid_from=None)
        branch=deepcopy(online);branch['channel']='branch'
        pages=[dict(id='web',url='https://hlbank.com.sg/rates'),dict(id='online',url='https://hlbank.com.sg/online-hlb-terms.pdf'),dict(id='branch',url='https://hlbank.com.sg/branch-hlb-terms.pdf'),dict(id='gift',url='https://hlbank.com.sg/gift.pdf',terms_role='bonus')]
        terms=[self.term(pid,'web','Effective 24 September 2026'),self.term(pid,'online','valid from 24 September 2026'),self.term(pid,'branch','valid from 23 September 2026'),self.term(pid,'gift','valid from 22 September 2026')]
        bind_primary_terms([online,branch],terms,pages,'vlm')
        self.assertEqual(online['valid_from'],'2026-09-24');self.assertIsNone(branch['valid_from'])
        self.assertIn('2026-09-23,2026-09-24',branch['conditions']);self.assertNotIn('2026-09-22',branch['conditions'])

    def test_ocbc_per_channel_maximum_and_individual_eligibility(self):
        pid='ocbc-sgd-promo';rows=[offer('OCBC',pid),offer('OCBC',pid)]
        rows[0]['channel']='online';rows[1]['channel']='branch'
        for r in rows:r.update(audience='all',amount_max=None,fresh_funds='unknown')
        terms=[self.term(pid,'pdf','S$999,999 for online placements; S$5,000,000 for placements at OCBC branches. Only personal accounts held by individual(s) are eligible. The placement amount must be in fresh funds only.')]
        bind_primary_terms(rows,terms,[dict(id='pdf',url='https://ocbc.com/terms.pdf')],'vlm')
        self.assertEqual([r['amount_max'] for r in rows],['999999','5000000'])
        self.assertTrue(all(r['audience']=='personal' and r['fresh_funds']=='yes' and r['max_inclusive'] for r in rows))

    def test_sbi_aggregate_limit_is_not_a_placement_limit(self):
        pid='sbi-sgd-promo';r=offer('SBI',pid);r.update(amount_max=None,valid_from=None)
        terms=[self.term(pid,'sbi','Multiple deposits can be placed as long as the maximum amount per individual is less than $1,000,000. Applicable for fresh and renewal of funds. per individual or per joint account. Walk in to any of our branches.')]
        bind_primary_terms([r],terms,[dict(id='sbi',url='https://sg.statebank/sgd-promotions')],'vlm')
        self.assertIsNone(r['amount_max']);self.assertIn('个人多笔合计 < SGD 1000000',r['conditions']);self.assertEqual(r['channel'],'branch');self.assertIsNone(r['valid_from'])

    def test_null_and_printed_sgd_prefix_are_bounded(self):
        self.assertEqual(bound('null',True,upper=True),(None,False));self.assertEqual(parse_money('SGD$10,000'),'10000')
        with self.assertRaises(ValueError):parse_money('USD$10,000')

if __name__=='__main__':unittest.main()

from copy import deepcopy
import unittest
from market_rates.demo import offer
from market_rates.extraction_contract import dates_in_quote
from market_rates.multi_bank_extractor import bind_primary_terms,bound,parse_money,rate_value
from market_rates.multi_bank_validation import matched_offers

class MultiBankTests(unittest.TestCase):
    def test_strict_upper_amount_preserves_fractional_dollar_boundary(self):
        self.assertEqual(bound('< S$100,000',True,upper=True),('100000',False))
        self.assertEqual(bound('≤ S$100,000',False,upper=True),('100000',True))
        with self.assertRaises(ValueError):bound('> S$100,000',True,upper=True)

    def test_cimb_literal_currency_typo_is_bounded(self):
        self.assertEqual(parse_money('$S$10,000'),'10000')
        for value in ['USD10,000','about S$10,000','S$10,00','$SG$10,000']:
            with self.assertRaises(ValueError):parse_money(value)

    def test_abbreviated_campaign_dates(self):
        self.assertEqual(dates_in_quote('available from 25 Sep 2026'),{'2026-09-25'})

    def test_both_lanes_agreeing_on_invented_endpoint_is_not_enough(self):
        row=offer('HLF','hlf-branch-promo');row.update(amount_max='99999',max_inclusive=True)
        pages=[dict(id='HLF',url='https://www.hlf.com.sg/promo')]
        terms=[dict(product_id=row['product_id'],page_id='HLF',locator='image.png',text='S$20,000 to < S$100,000')]
        with self.assertRaisesRegex(ValueError,'not printed'):bind_primary_terms([row],terms,pages,'vlm')

    def test_bonus_campaign_must_not_supply_base_campaign_bounds_or_dates(self):
        row=offer('CIMB','cimb-wwfd-online');row.update(valid_from=None,valid_to=None,amount_max=None,fresh_funds='unknown')
        pages=[dict(id='bonus',url='https://www.cimb.com.sg/wwfd-i-promo.pdf'),dict(id='base',url='https://www.cimb.com.sg/tnc-wwfd-2026.pdf')]
        terms=[dict(product_id=row['product_id'],page_id='bonus',locator='bonus.png',text='valid from 1 September 2026 to 30 September 2026 maximum of S$200,000 per placement'),
               dict(product_id=row['product_id'],page_id='base',locator='base.png',text='valid from 21 September 2026 to 30 September 2026 maximum of S$1,000,000 per placement')]
        bind_primary_terms([row],terms,pages,'vlm')
        self.assertEqual(row['valid_from'],'2026-09-21');self.assertEqual(row['amount_max'],'1000000')

    def test_missing_or_changed_tier_blocks_whole_product_group(self):
        a=offer();b=offer(audience='premier',rate='2.0');run=dict(llm=dict(offers=[a,b]),vlm=dict(offers=[deepcopy(a)]))
        good,bad=matched_offers(run);self.assertEqual(good,[]);self.assertEqual(len(bad),1)
        run['vlm']['offers'].append(deepcopy(b));self.assertEqual(len(matched_offers(run)[0]),2)
        run['vlm']['offers'][1]['max_inclusive']=True;self.assertEqual(matched_offers(run)[0],[])

    def test_duplicate_tiers_do_not_pass_the_set_comparison(self):
        a=offer();run=dict(llm=dict(offers=[a,a]),vlm=dict(offers=[a,a]))
        self.assertEqual(matched_offers(run)[0],[])

    def test_explicit_welcome_minimum_maximum_include_endpoints(self):
        row=offer('CIMB','cimb-preferred-welcome');row['max_inclusive']=False
        terms=[dict(product_id=row['product_id'],page_id='welcome',locator='welcome.png',text='Minimum S$10,000 Maximum S$250,000 New-to-Preferred customers')]
        bind_primary_terms([row],terms,[dict(id='welcome',url='https://www.cimbpreferred.com.sg/ntp-fd.pdf')],'vlm')
        self.assertEqual((row['amount_min'],row['amount_max'],row['min_inclusive'],row['max_inclusive']),('10000','250000',True,True))
        self.assertEqual(row['channel'],'unknown')

    def test_compound_or_ambiguous_rates_rejected(self):
        for value in ['1.7% / 1.8%','up to 1.8%','1.8% cashback','NaN']:
            with self.assertRaises(ValueError):rate_value(value)

if __name__=='__main__':unittest.main()

from copy import deepcopy
import unittest
from market_rates.demo import offer
from market_rates.extraction_contract import parse_tenor
from market_rates.multi_bank_extractor import bind_primary_terms

class ExpansionTests(unittest.TestCase):
    def test_year_and_chinese_month_units_are_explicit(self):
        self.assertEqual(parse_tenor('1 year'),(12,'M'));self.assertEqual(parse_tenor('8个月'),(8,'M'))
        with self.assertRaises(ValueError):parse_tenor('1')

    def test_uob_terms_are_tenor_scoped_not_mixed(self):
        r=offer('UOB','uob-sgd-promo');r.update(amount_min=None,amount_max=None,valid_from=None,valid_to=None)
        pages=[dict(id='web',url='https://www.uob.com.sg/rates'),dict(id='six',url='https://www.uob.com.sg/6.pdf'),dict(id='ten',url='https://www.uob.com.sg/10.pdf')]
        def t(pid,text):return dict(product_id=r['product_id'],page_id=pid,locator=pid,text=text)
        terms=[t('web','Online placements are capped at S$999,999 per placement.'),t('six','UOB Singapore Dollar 6 Months Fixed Deposit Promotion. a Fresh Funds deposit of a minimum sum of SGD10,000. account opened by an individual. period commencing on 23 September 2026 and ending on 31 October 2026'),t('ten','UOB Singapore Dollar 10 Months Fixed Deposit Promotion. a minimum sum of SGD90,000')]
        bind_primary_terms([r],terms,pages,'vlm')
        self.assertEqual((r['amount_min'],r['amount_max']),('10000','999999'));self.assertEqual(r['fresh_funds'],'yes');self.assertEqual(r['valid_to'],'2026-10-31')

    def test_boc_rate_validity_is_not_new_customer_campaign_validity(self):
        r=offer('BOC','boc-sgd-welcome');r['valid_from']=None
        text='手机银行。** 2026年9月14日至2026年10月31日（含首尾两日），新客户。附带其他规则与条款。本次个人定期存款促销利率有效期为2026年9月21日至2026年9月27日。以上定期存款促销利率适用于个人客户'
        terms=[dict(product_id=r['product_id'],page_id='boc',locator='boc.png',text=text)]
        bind_primary_terms([r],terms,[dict(id='boc',url='https://www.bankofchina.com/sg/rate')],'vlm')
        self.assertEqual((r['valid_from'],r['valid_to']),('2026-09-21','2026-09-27'));self.assertEqual(r['channel'],'online')
        self.assertIn('2026年10月31日',r['conditions'])

if __name__=='__main__':unittest.main()

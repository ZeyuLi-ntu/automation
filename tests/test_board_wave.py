import unittest
from market_rates.board_wave import tenor_values,amount_band,normalize_section
from market_rates.workbook_policy import presentation_currency,currency_in_scope

class BoardWaveTests(unittest.TestCase):
    def section(self,bank,rows,pid='test-board',currency='SGD',table=0):
        return dict(id=pid,bank=bank,currency=currency,rows=rows,product_id=pid,table=table,page_id='source')

    def test_currency_mapping_is_presentation_only(self):
        from market_rates.scope import currency_code
        self.assertEqual(currency_code('CNH'),'CNH')
        self.assertEqual(presentation_currency('CNH'),'CNY')
        self.assertFalse(currency_in_scope('JPY'))
        self.assertTrue(currency_in_scope('CNH'))

    def test_source_tenor_lists_ranges_and_hyphens(self):
        self.assertEqual(tenor_values('1-month'),[(1,'M')])
        self.assertEqual(tenor_values('3,4,5',True),[(3,'M'),(4,'M'),(5,'M')])
        self.assertEqual(tenor_values('6 - 8',True),[(6,'M'),(7,'M'),(8,'M')])
        self.assertEqual(tenor_values('1 to 2 Weeks'),[])

    def test_bounds_keep_missing_minimum_and_exclusions(self):
        self.assertEqual(amount_band('Below S$50,000'),(None,'50000',True,False))
        self.assertEqual(amount_band('>S$20,000 - S$50,000'),('20000','50000',False,True))
        self.assertEqual(amount_band('$500 to < $50,000'),('500','50000',True,False))

    def test_singfinance_two_level_headers_are_not_data(self):
        rows=[['Tenure','Deposit Amount'],['$500 to < $50,000','$50,000 and above'],['1 month','0.0500% p.a.','0.1000% p.a.'],['3 months','0.1000% p.a.','0.1500% p.a.']]
        offers=normalize_section(self.section('SingFinance',rows),'llm')
        self.assertEqual(len(offers),4);self.assertEqual(offers[0]['amount_min'],'500');self.assertEqual(offers[-1]['rate_pct'],'0.15')
        self.assertEqual(offers[-1]['tenor_value'],3)

    def test_unknown_annual_unit_stays_unknown(self):
        rows=[['Months','S$5,000 - S$20,000'],['12','0.50%']]
        # Three physical columns match the actual OCBC layout contract.
        rows=[['Tenure (months)','S$5,000 - S$20,000','>S$20,000 - S$50,000'],['24 (new placements not available*)','0.50%','0.10%']]
        offers=normalize_section(self.section('OCBC',rows),'vlm')
        self.assertTrue(all(o['rate_basis']=='unknown' for o in offers))
        self.assertTrue(all('旧存款续期' in o['conditions'] for o in offers))

    def test_maybank_excludes_jpy_without_dropping_other_currency(self):
        rows=[['Foreign Currency Time Deposit (% p.a.) - Tier 1'],['Month(s)'],['Currency','Minimum','1','3'],['US Dollar','10K','3.25','3.45'],['Japanese Yen','2.5M','0.45','0.5']]
        offers=normalize_section(self.section('Maybank',rows,'maybank-fx-tier1-board','FX',5),'llm')
        self.assertEqual(len(offers),2);self.assertTrue(all(o['currency']=='USD' for o in offers));self.assertEqual(offers[0]['amount_min'],'10000')

    def test_rhb_short_term_is_not_personal(self):
        rows=[['Deposit Amount','1-mth*','3-mth'],['$20,000 to $200,000','0.1','0.3']]
        offers=normalize_section(self.section('RHB',rows),'llm')
        self.assertEqual(offers[0]['audience'],'unknown');self.assertIn('Corporate',offers[0]['conditions']);self.assertEqual(offers[1]['audience'],'personal')

if __name__=='__main__':unittest.main()

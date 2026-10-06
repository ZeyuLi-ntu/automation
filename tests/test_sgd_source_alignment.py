import unittest
from market_rates.sgd_source_alignment import align_tables

class AlignmentTests(unittest.TestCase):
    def test_icbc_own_grid_recovers_year_and_missing_tiers(self):
        row=dict(bank='ICBC',product_id='icbc-sgd-promo',tenor_value=36,tenor_unit='M',channel='branch_or_instruction',amount_min='20000',rate_pct='9.99',evidence=[dict(page_id='p')])
        terms=[dict(page_id='p',product_id='icbc-sgd-promo',locator='own.png',text='SGD Counter Promotion Rates Tenor SGD20K (inclusive) to SGD200K SGD200K (inclusive) & Above 1 month 1.10% 1.10% 1 year 1.70% 1.75%')]
        rows=[row];align_tables(rows,terms,[],'vlm')
        self.assertEqual(len(rows),4)
        self.assertEqual([(r['tenor_value'],r['rate_pct']) for r in rows],[(1,'1.1'),(1,'1.1'),(12,'1.7'),(12,'1.75')])
        self.assertTrue(all(r['channel']=='branch' for r in rows))
        self.assertEqual(rows[0]['amount_max'],'200000');self.assertFalse(rows[0]['max_inclusive']);self.assertIsNone(rows[-1]['amount_max'])

    def test_printed_thousands_amount(self):
        from market_rates.multi_bank_extractor import parse_money
        self.assertEqual(parse_money('20K'),'20000')
        self.assertEqual(parse_money('S$2.5k'),'2500.0')
        with self.assertRaises(ValueError):parse_money('20KB')

    def test_cimb_uses_row_and_customer_column(self):
        row=dict(bank='CIMB',product_id='cimb-sgd-online',tenor_value=6,tenor_unit='M',audience='preferred',rate_pct='1.4',evidence=[])
        pages=[dict(id='p',units=[dict(kind='rates',product_ids=['cimb-sgd-online'],text='PERSONAL BANKING\nPREFERRED BANKING\n3 Months\t1.35\t1.40\n6 Months\n1.75\n1.80')])]
        self.assertEqual(len(align_tables([row],[],pages,'llm')),1);self.assertEqual(row['rate_pct'],'1.8')
        row['rate_pct']='1.4';self.assertEqual(align_tables([row],[],pages,'vlm'),[]);self.assertEqual(row['rate_pct'],'1.4')

    def test_hlf_bound_comes_from_own_vision_transcript(self):
        row=dict(bank='HLF',product_id='hlf-branch-promo',tenor_value=9,amount_min='20000',amount_max=None,max_inclusive=False,rate_pct='1.55',evidence=[dict(page_id='p')])
        terms=[dict(page_id='p',product_id='hlf-branch-promo',locator='own.png',text='Deposit Amount\nS$20,000 to < S$100,000\t1.45%\t1.55%\t1.65%\nPublished rates')]
        align_tables([row],terms,[],'vlm');self.assertEqual(row['amount_max'],'100000');self.assertFalse(row['max_inclusive'])
        row['rate_pct']='1.99'
        with self.assertRaisesRegex(ValueError,'rate does not match'):align_tables([row],terms,[],'vlm')

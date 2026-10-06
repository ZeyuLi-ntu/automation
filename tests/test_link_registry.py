import unittest
from unittest.mock import patch
from market_rates.link_registry import bank_link
from market_rates.remaining_banks import configuration


class LinkRegistryTests(unittest.TestCase):
    def setUp(self):
        self.cells={'A45':'maybank','B45':'others','C45':'促销','D45':None,
            'C46':'挂牌','D46':'https://sslsecure.maybank.com.sg/board',
            'B47':'SGD','C47':'促销','D47':'https://www.maybank2u.com.sg/new-promotion',
            'C48':'挂牌','D48':'https://sslsecure.maybank.com.sg/board'}

    def read(self):return bank_link('user-links.xlsx','Maybank','SGD','促销',['www.maybank2u.com.sg'])

    def test_latest_cell_used_and_board_rate_not_selected(self):
        with patch('market_rates.link_registry.read_xlsx',return_value={'Links':self.cells}):
            self.assertEqual(self.read()['cell'],'D47')
            self.cells['D47']='https://www.maybank2u.com.sg/revised-url'
            cfg=configuration('Maybank',links='user-links.xlsx')
            self.assertEqual(cfg['sources'][0]['urls'],[self.cells['D47']])
            self.assertIn('section_between',cfg['sources'][0]['capture_units'][0])
            self.assertFalse(cfg['pdf_rate_products'])

    def test_missing_duplicate_and_unregistered_urls_stop(self):
        with patch('market_rates.link_registry.read_xlsx',return_value={'Links':self.cells}):
            self.cells['D47']=None
            with self.assertRaises(ValueError):self.read()
            self.cells['D47']='https://www.maybank2u.com.sg.evil.invalid/rates'
            with self.assertRaises(ValueError):self.read()
            self.cells['D47']='https://www.maybank2u.com.sg/rates'
            self.cells.update(C49='促销',D49='https://www.maybank2u.com.sg/another')
            with self.assertRaises(ValueError):self.read()


if __name__=='__main__':unittest.main()

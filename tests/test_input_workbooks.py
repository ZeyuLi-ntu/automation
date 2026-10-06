import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from market_rates.input_workbooks import configuration,save_configuration,validate,REPORT_SHEETS,RAINBOW_SHEETS

class InputWorkbookTests(unittest.TestCase):
    def test_bad_selection_keeps_previous_setting(self):
        with TemporaryDirectory() as t:
            path=Path(t)/'selection.json';save_configuration('latest',path=path)
            with self.assertRaisesRegex(ValueError,'存在'):save_configuration('selected','missing.xlsx','also-missing.xlsx',path=path)
            self.assertEqual(configuration(path)['mode'],'latest')

    def test_missing_sheet_has_specific_message(self):
        with TemporaryDirectory() as t:
            a=Path(t)/'新 调研.xlsx';b=Path(t)/'新 彩虹.xlsx';a.touch();b.touch()
            with patch('market_rates.input_workbooks.read_xlsx',return_value={}):
                with self.assertRaisesRegex(ValueError,'缺少工作表'):validate(a,b)

    def test_selected_paths_support_spaces_and_no_original_write(self):
        with TemporaryDirectory() as t:
            a=Path(t)/'新 调研.xlsx';b=Path(t)/'新 彩虹.xlsx';a.write_bytes(b'unchanged-a');b.write_bytes(b'unchanged-b')
            report={n:{} for n in REPORT_SHEETS};rainbow={n:{} for n in RAINBOW_SHEETS}
            for n,bc in [('SGD促销','A'),('USD促销','B'),('CNY促销','A'),('USD挂牌','B'),('CNY挂牌','A')]:report[n][bc+'3']='银行'
            rainbow['USD Rate + Other Currency Rates']['A31']='USD Board Rates'
            with patch('market_rates.input_workbooks.read_xlsx',side_effect=[report,rainbow]):
                result=save_configuration('selected',a,b,path=Path(t)/'selection.json')
            self.assertEqual(result['report'],str(a.resolve()));self.assertEqual(a.read_bytes(),b'unchanged-a')
            self.assertEqual(b.read_bytes(),b'unchanged-b')

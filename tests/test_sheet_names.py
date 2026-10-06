import unittest
from market_rates.sheet_names import unused_sheet_name

class SheetNamesTest(unittest.TestCase):
    def test_both_outputs_and_case(self):
        self.assertEqual(unused_sheet_name('Input', {'INPUT': {}}, {'Input_2': {}}), 'Input_3')

    def test_excel_length_with_suffix(self):
        stem='x'*40
        self.assertEqual(unused_sheet_name(stem, {'x'*31: {}}), 'x'*29+'_2')

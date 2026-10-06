from copy import deepcopy
from pathlib import Path
import importlib.util
import tempfile
import unittest
from zipfile import ZipFile
from market_rates.table_validation import stable_blocks
from market_rates.xlsx_read import read_xlsx


class TableValidationTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('openpyxl'), '完整Excel检查使用随附表格环境；基础爬虫环境无需此依赖')
    def test_insertion_moves_only_affected_local_and_cross_sheet_references(self):
        from scripts.check_table_validation import shifted_formula
        self.assertEqual(shifted_formula('=C51-D51',True),'=D51-E51')
        self.assertEqual(shifted_formula('=SGD促销!C60+USD促销!C60'), '=SGD促销!D60+USD促销!C60')
        self.assertEqual(shifted_formula("='最高报价汇总 '!F2",True),"='最高报价汇总 '!F2")

    def test_changed_personal_rate_changes_position_and_ties_keep_previous_order(self):
        rows=[{'bank':'A','rank_rate':'0.017','prior_index':0},
              {'bank':'SCB','rank_rate':'0.017','prior_index':1},
              {'bank':'B','rank_rate':'0.016','prior_index':2}]
        self.assertEqual([r['bank'] for r in stable_blocks(rows)],['A','SCB','B'])
        changed=deepcopy(rows);changed[1]['rank_rate']='0.018'
        self.assertEqual([r['bank'] for r in stable_blocks(changed)],['SCB','A','B'])
        self.assertEqual(rows[1]['rank_rate'],'0.017')

    def test_new_product_on_equal_rate_follows_previous_products(self):
        rows=[{'bank':'SCB-new','rank_rate':'0.017','prior_index':2},
              {'bank':'SCB-old','rank_rate':'0.017','prior_index':1},
              {'bank':'A','rank_rate':'0.017','prior_index':0}]
        self.assertEqual([r['bank'] for r in stable_blocks(rows)],['A','SCB-old','SCB-new'])

    def test_legal_empty_inline_string_cell_is_not_a_reader_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'empty-inline.xlsx'
            with ZipFile(path,'w') as z:
                z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Example" sheetId="1" r:id="rId1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"/><c r="B1" t="inlineStr"><is><t>SCB</t></is></c></row></sheetData></worksheet>')
            self.assertEqual(read_xlsx(path)['Example'],{'A1':None,'B1':'SCB'})

from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
from market_rates.demo import offer
from market_rates.export import make_plan
from market_rates.common import load
from market_rates.rules import build_views
from market_rates.workbook_policy import bank_blocks,daily_change_cells,workbook_policy,included_groups
from market_rates.xlsx_read import read_xlsx


class WorkbookPolicyTests(unittest.TestCase):
    def test_comparison_recognizes_already_shifted_formula(self):
        cells={'IG4':'当日最高报价变动','IG5':'=D5-E5','IG9':'=IF(COUNT(C9,D9)=2,C9-D9,"-")','IE5':'=D5-G5'}
        self.assertEqual(daily_change_cells(cells),['IG5','IG9'])

    def test_bank_personal_rank_beats_other_products_special_rate(self):
        def block(bank,product,audience,rate,prior):
            return dict(bank=bank,rank_rate=str(Decimal(rate)/100),prior_index=prior,
                        group=dict(product_id=product,details=[dict(audience=audience,rate_pct=rate)]))
        original=[block('A','welcome','preferred','2.33',0),block('B','base','personal','1.80',1),block('A','base','personal','1.75',0)]
        result=bank_blocks(original)
        self.assertEqual([(b['bank'],b['group']['product_id']) for b in result],[('B','base'),('A','base'),('A','welcome')])
        self.assertEqual(result[1]['bank_rank_rate'],'0.0175')

    def test_equal_bank_rates_preserve_prior_bank_order(self):
        blocks=[dict(bank='A',rank_rate='0.017',prior_index=3),dict(bank='B',rank_rate='0.017',prior_index=1)]
        self.assertEqual([b['bank'] for b in bank_blocks(blocks)],['B','A'])

    def test_deferred_quote_cannot_leak_into_excel_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'report.xlsx';source.write_bytes(b'fixture');rainbow=root/'rainbow.xlsx';rainbow.write_bytes(b'fixture')
            offers=[offer('CIMB','cimb-sgd-online',rate='1.75'),offer('CIMB','cimb-sgd-online',audience='preferred',rate='1.8'),offer('CIMB','cimb-preferred-welcome',audience='preferred',rate='2.33')]
            views=build_views(offers,{}, {},'2026-09-25')
            result=dict(views,pending=0,demo=True,run_id='test',as_of='2026-09-25');before=deepcopy(result)
            mapping=dict(template_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),entries=[dict(group_id=g['id'],row=5,expected_bank_label='CIMB',confirmed=True) for g in views['groups'] if g['product_id']=='cimb-sgd-online'])
            book={'SGD促销':{'A5':'CIMB','C5':'0.0175','D5':'0.0165','IF4':'当日最高报价变动','IF5':'=C5-D5'},'最高报价汇总 ':{'B4':'CIMB'}}
            with patch('market_rates.export.read_xlsx',return_value=book):
                plan=load(make_plan(result,{},mapping,source,rainbow,root/'output'))
            self.assertEqual(len(plan['groups']),1)
            self.assertEqual(plan['highest']['CIMB/6M']['rate_pct'],'1.8')
            self.assertEqual(result,before)

    def test_default_policy_remembers_deferred_products(self):
        self.assertEqual(set(workbook_policy()['deferred_product_ids']),{'cimb-wwfd-online','cimb-preferred-welcome','hlf-digital-promo','boc-sgd-welcome'})

    def test_boc_welcome_all_tenors_excluded_without_dropping_mobile(self):
        groups=[dict(bank='BOC',product_id=p,tenor=t) for p in ['boc-sgd-welcome','boc-sgd-mobile'] for t in ['4M','8M']]
        before=deepcopy(groups)
        selected=included_groups(groups,workbook_policy())
        self.assertEqual(len(selected),2)
        self.assertTrue(all(g['product_id']=='boc-sgd-mobile' for g in selected))
        self.assertEqual(groups,before)

    def test_hidden_formula_inside_merge_is_not_another_visible_change(self):
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        parts={
            'xl/_rels/workbook.xml.rels':'<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
            'xl/workbook.xml':f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="SGD促销" r:id="r1"/></sheets></workbook>',
            'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{ns}"><sheetData><row r="55"><c r="IF55"><f>C55-D55</f></c></row><row r="56"><c r="IF56"><f>AW56-BT56</f></c></row></sheetData><mergeCells><mergeCell ref="IF55:IF56"/></mergeCells></worksheet>'}
        archive=MagicMock();archive.__enter__.return_value=archive;archive.namelist.return_value=list(parts);archive.read.side_effect=lambda name:parts[name].encode()
        with patch('market_rates.xlsx_read.zipfile.ZipFile',return_value=archive):
            cells=read_xlsx('memory',formulas=True,merge_anchors_only=True)['SGD促销']
        self.assertEqual(cells,{'IF55':'=C55-D55'})


if __name__=='__main__':unittest.main()

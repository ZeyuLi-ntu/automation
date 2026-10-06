import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from market_rates.board_coverage import audit, required_scope, dated, HEADERS, html_report


def book(cells=None):
    data={'B1':'Bank List',**{chr(71+i)+'1':v for i,v in enumerate(HEADERS)}}
    data.update(cells or {})
    return {'Bank List':data}


def detail(cur='USD',insertable=True,**kw):
    return dict(bank='DBS',currency=cur,insertable=insertable,
        hold_reason='' if insertable else '原表未明确年化口径，待人工核实',
        evidence_date='2026-09-28',manual_reviewed=False,**kw)


class BoardCoverageTests(unittest.TestCase):
    def test_required_dates_not_observed_rows(self):
        fixture=book({'B2':'DBS/POSB','H2':'20260916','J2':'20260916','B3':'TRUST','G3':'20260909','B4':'MARI','G4':'20260909'})
        with patch('market_rates.board_coverage.read_xlsx',return_value=fixture):
            rows=required_scope('unused')
        self.assertEqual([(r['bank'],r['currency'],r['cell']) for r in rows],[('DBS','USD','H2'),('DBS','AUD','J2')])

    def test_bad_marker_and_missing_bank_list_fail_closed(self):
        for fixture in [book({'B2':'BEA','G2':'已检查'}),{}]:
            with patch('market_rates.board_coverage.read_xlsx',return_value=fixture),self.assertRaises(ValueError):
                required_scope('unused')

    def test_date_formats_do_not_mean_current_quote(self):
        self.assertTrue(all(dated(v) for v in ['20260916','2026-09-16','2026/9/16','46281']))
        self.assertFalse(any(dated(v) for v in ['20260230','-','1.5','']))

    def result(self, details, cells=None, saved=None):
        fixture=book(cells or {'B2':'DBS/POSB','H2':'20260916','J2':'20260916'})
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.xlsx';source.write_bytes(b'fixture')
            output=Path(td)/'output.xlsx';output.write_bytes(b'fixture')
            p=dict(as_of='2026-09-28',source_run='run',details=details,report_output=str(output),
                matrices=[dict(currency='AUD',sheet='AUD挂牌',groups=[dict(bank='DBS',target_row=3,rows=[dict(values=[dict(col=4,expected=0.03)])])])],
                histories=[dict(currency='USD',sheet='USD挂牌',current_col=4,existing=[dict(bank='DBS',address='D5',expected=0.035)],inserts=[])])
            def read(path,**kw): return saved if Path(path)==output else fixture
            with patch('market_rates.board_coverage.read_xlsx',side_effect=read):
                return audit(p,source,inspect_saved=saved is not None)

    def test_missing_pair_is_not_covered_by_another_currency(self):
        r=self.result([detail()])
        self.assertEqual(r['required_count'],2)
        self.assertEqual(r['counts'],{'present':1,'missing':1})
        self.assertFalse(r['required_pair_availability_complete'])
        self.assertEqual(r['pairs_with_numeric_output'],1)

    def test_human_pending_is_not_technical_block(self):
        r=self.result([detail(),detail('AUD')])
        self.assertEqual(r['counts'],{'present':2})
        self.assertEqual(r['rows'][0]['human_accepted_count'],0)

    def test_saved_current_not_old_history_is_used(self):
        r=self.result([detail(),detail('AUD')],saved={'USD挂牌':{'D5':'-','E5':'0.035'},'AUD挂牌':{'D3':'0'}})
        self.assertTrue(r['saved_output_inspected'])
        self.assertEqual(r['counts'],{'write_gap':1,'present':1})
        self.assertEqual(r['pairs_with_numeric_output'],1)

    def test_blocks_partial_and_future_date_remain_separate(self):
        r=self.result([detail(insertable=False),detail('AUD'),detail('AUD',False)])
        self.assertEqual(r['counts'],{'held':1,'partial':1})
        self.assertEqual(r['rows'][0]['held_count'],1)
        self.assertEqual(r['pairs_with_numeric_output'],1)

    def test_cnh_maps_to_cny_without_extra_requirement(self):
        r=self.result([detail('CNH')],cells={'B2':'DBS','I2':'20260916'})
        self.assertEqual(r['rows'][0]['detail_count'],1)
        self.assertEqual(r['rows'][0]['status'],'write_gap')
        self.assertEqual(r['extra_pairs'],[])

    def test_html_discloses_scope_not_just_numeric_success(self):
        text=html_report(self.result([detail()]))
        self.assertIn('应有 2 组',text)
        self.assertIn('缺当前数值 1 组',text)
        self.assertIn('尚未抓取',text)
        self.assertIn('不把',self.result([detail()])['completeness_claim'])


if __name__=='__main__':unittest.main()

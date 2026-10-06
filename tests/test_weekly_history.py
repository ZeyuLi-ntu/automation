from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from market_rates.common import save
from market_rates.demo import offer
from market_rates.rules import build_views
from market_rates.weekly_history import identity,column_mode,date_value,apply_overrides,baseline
from market_rates.weekly_history import approve

class WeeklyHistoryTests(unittest.TestCase):
    def test_same_day_refresh_new_week_insert_old_date_refused(self):
        self.assertEqual(column_mode('2026-09-26','2026-09-26'),0)
        self.assertEqual(column_mode('2026-10-03','2026-09-26'),1)
        with self.assertRaises(ValueError):column_mode('2026-09-19','2026-09-26')

    def test_manual_rate_survives_wording_but_not_changed_eligibility(self):
        row=offer();record={'overrides':{identity(row):dict(fields={'rate_pct':'2.17'},reason='用户核对')}}
        row['conditions']='different OCR wording';new,applied=apply_overrides([row],record)
        self.assertEqual(new[0]['rate_pct'],'2.17');self.assertNotEqual(row['rate_pct'],'2.17');self.assertEqual(len(applied),1)
        row['amount_min']='500000';new,applied=apply_overrides([row],record)
        self.assertEqual(applied,[])

    def test_override_does_not_reanimate_expired_or_missing_offer(self):
        row=offer();row['valid_to']='2026-09-30'
        record={'overrides':{identity(row):dict(fields={'rate_pct':'2.17'},reason='用户核对')}}
        new,_=apply_overrides([row],record)
        self.assertEqual(build_views(new,{}, {},'2026-10-03')['groups'],[])
        self.assertEqual(apply_overrides([],record),([],[]))

    def test_approval_pointer_is_hash_bound(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);save(root/'history/latest-approved.json',{'id':'example','sha256':'bad'})
            save(root/'history/example/approval.json',{})
            with self.assertRaisesRegex(ValueError,'登记被修改'):baseline(root)

    def test_excel_dates_read_consistently(self):
        self.assertEqual(date_value(datetime(2026,9,26)),'2026-09-26')
        self.assertEqual(date_value('46291'),'2026-09-26')

    def test_excel_float_noise_is_not_registered_as_manual_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';out.mkdir();row=offer(rate='1.35');row['input_row']=4
            for f in ['report.xlsx','rainbow.xlsx']:(out/f).write_bytes(b'fixture')
            plan=dict(as_of='2026-09-26',input_sheet='input',details=[row],groups=[],banks=['DEMO_A'],bank_dates={'DEMO_A':'2026-09-26'},report_output=str(out/'report.xlsx'),rainbow_output=str(out/'rainbow.xlsx'))
            save(out/'table-validation-plan.json',plan);save(out/'table-validation-checks.json',dict(passed=1,total=1))
            cells={'SGD促销':{'C3':'46291'},'input':{'H4':'0.013500000000000002','B4':row['product_name']}}
            with patch('market_rates.weekly_history.read_xlsx',return_value=cells):result=approve(root,out,'测试用明确人工确认')
            self.assertEqual(result['overrides'],{})

if __name__=='__main__':unittest.main()

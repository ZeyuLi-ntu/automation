"""Read-only integration assertions for rolling output."""
import argparse
from pathlib import Path
import openpyxl
from market_rates.common import load,save
from market_rates.table_validation import sha

p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--week',type=int,required=True);a=p.parse_args()
plan=load(a.plan);book=openpyxl.load_workbook(plan['report_output'],data_only=True);sheet=book['SGD促销']
group=next(g for g in plan['groups'] if g['product_id']=='cimb-sgd-online' and g['display_tenor']=='6M');row=group['report_row']
expected=[.0191,.0175] if a.week==1 else [.0203,.0191,.0175]
actual=[sheet.cell(row,c).value for c in range(3,3+len(expected))]
assert all(abs(x-y)<1e-12 for x,y in zip(actual,expected)),(actual,expected)
formulas=openpyxl.load_workbook(plan['report_output'])['SGD促销'];refs=[formulas.cell(row,c).value for c in range(3,3+len(expected))]
assert len({r.split('!')[0] for r in refs})==len(refs),refs
before=openpyxl.load_workbook(plan['report_template'],data_only=True)['SGD促销'];deltas={d['source'] for d in plan['deltas']};checked=0
for cells in before:
    for c in cells:
        if c.column<3 or c.coordinate in deltas:continue
        actual=sheet.cell(c.row,c.column+1).value
        assert actual==c.value or (isinstance(actual,(int,float)) and isinstance(c.value,(int,float)) and abs(actual-c.value)<1e-12),(c.coordinate,c.value,actual)
        checked+=1
for kind in ['report','rainbow']:assert sha(plan[kind+'_template'])==plan[kind+'_sha256']
save(Path(a.plan).parent/'weekly-value-checks.json',dict(passed=True,week=a.week,values=expected,formulas=refs,history_cells_checked=checked))
print('跨周 '+str(a.week)+'：历史报价保留，明细引用独立。')

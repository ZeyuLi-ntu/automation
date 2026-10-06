import argparse,re
from pathlib import Path
import openpyxl
from market_rates.common import load,save
from market_rates.table_validation import sha
from market_rates.sgd_comparison import check_saved
from market_rates.xlsx_read import read_xlsx,merged_ranges
from scripts.check_board_cleanup import check_deltas,equal

def check(out):
    out=Path(out);p=load(out/'table-validation-plan.json');before=read_xlsx(p['correction_source'],merge_anchors_only=True);after=read_xlsx(p['report_output'],merge_anchors_only=True)
    sg=check_saved(p['report_output'],after);sgcells={x['address'] for x in sg};delta_names=['USD促销','CNY促销','其他外币促销利率','USD挂牌','CNY挂牌']
    columns={n:next(re.match('[A-Z]+',a)[0] for a,v in after[n].items() if v in ['当日增幅','当日最高报价变动']) for n in delta_names};count=0
    for name,s in before.items():
        for a,v in s.items():
            if name=='SGD促销' and a in sgcells:continue
            if name in columns and re.match('[A-Z]+',a)[0]==columns[name] and v not in ['当日增幅','当日最高报价变动']:continue
            assert equal(after[name].get(a),v),(name,a,v,after[name].get(a));count+=1
    oldmerges=merged_ranges(p['correction_source']);newmerges=merged_ranges(p['report_output'])
    for entry in p['correction_bank_merges']:
        for a in entry['ranges']:assert a in newmerges[entry['sheet']],('bank merge',entry['sheet'],a)
    w=openpyxl.load_workbook(p['report_output']);checked_icons=0
    for name in delta_names+['SGD促销']:
        dc=columns.get(name,'IH')
        for cf,rules in w[name].conditional_formatting._cf_rules.items():
            if not any(area.min_col<=openpyxl.utils.column_index_from_string(dc)<=area.max_col for area in cf.sqref.ranges):continue
            for rule in rules:
                if rule.type=='iconSet':checked_icons+=1
    # Exact supplied examples: different floating representations must be zero.
    for row in [22,33,63,94]:
        address=columns['USD促销']+str(row);assert float(after['USD促销'][address])==0,(address,after['USD促销'][address])
    for row in [204,205]:assert after['SGD促销']['IH'+str(row)]=='无上期数据'
    counts=check_deltas(p['report_output'],after)
    assert sha(p['correction_source'])==p['correction_sha256']
    result=dict(passed=True,preserved_cells=count,comparison_rows=counts,sgd=sg,icon_rules=checked_icons)
    save(out/'correction-checks.json',result);print('Delta correction saved checks:',count,'unchanged cells;',counts)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);check(a.parse_args().out)

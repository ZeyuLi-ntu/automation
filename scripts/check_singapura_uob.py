"""Saved numbers, formulas and display bands for the two requested fixes."""
import argparse,re
from pathlib import Path
from market_rates.common import load,save
from market_rates.xlsx_read import read_xlsx,merged_ranges
from market_rates.board_plan import col,cell_number
from market_rates.board_batch_plan import label_tenor
from market_rates.sgd_comparison import check_saved
from scripts.check_four_scope_fixes import blocks

def check(out):
    out=Path(out);p=load(out/'table-validation-plan.json');base=load(p['base_plan'])
    book=read_xlsx(p['report_output'],merge_anchors_only=True);merges=merged_ranges(p['report_output'])
    comparisons=check_saved(p['report_output'],book);s=book['SGD挂牌']
    spans=blocks(s,merges['SGD挂牌'],1,'Singapura Finance');assert len(spans)==1
    first,end=spans[0];assert end-first+1==2
    expected_labels=['SGD <50,000','SGD ≥50,000'];checks=[]
    for r,label in zip(range(first,end+1),expected_labels):
        assert str(s['B'+str(r)]).startswith(label)
        assert '1–2M起存5,000' in s['B'+str(r)]
        rs=[q for q in base['details'] if q['bank']=='Singapura Finance' and q['currency']=='SGD' and (q['amount_max']=='50000')==(r==first)]
        for c in range(3,19):
            t=label_tenor(s.get(col(c)+'2'));rates=[float(q['rate_pct'])/100 for q in rs if str(q['tenor_value'])+q['tenor_unit']==t]
            expected=max(rates) if rates else '-';actual=cell_number(s.get(col(c)+str(r)))
            assert abs(actual-expected)<1e-10 if rates else actual==expected
            checks.append(dict(cell=col(c)+str(r),passed=True))
    save(out/'singapura-uob-checks.json',dict(passed=True,board_checks=checks,comparisons=comparisons))
    promo=book['SGD促销'];delta=re.match('[A-Z]+',comparisons[0]['address'])[0];dc=0
    for letter in delta:dc=26*dc+ord(letter)-64
    views=[dict(sheet='SGD挂牌',start=first,end=end,bank_col=1,current_col=3,last_col=19,name='singapura-sgd-two-bands')]
    for bank,name in [('UOB','uob-sgd-change'),('Singapura Finance','singapura-sgd-change')]:
        r=next(x for x in comparisons if x['bank']==bank and isinstance(x['expected'],(int,float)))
        views.append(dict(sheet='SGD促销',start=r['row'],end=r['end'],bank_col=1,current_col=3,last_col=dc,compact_history=True,keep_history_columns=3,name=name))
    save(out/'singapura-uob-previews.json',views)
    print('Singapura 2 bands and',len(comparisons),'UOB/Singapura comparison blocks passed.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);check(p.parse_args().out)

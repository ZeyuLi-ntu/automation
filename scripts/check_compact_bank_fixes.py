"""Check the seven requested layout repairs against the saved source offers."""
import argparse,re
from pathlib import Path
from collections import defaultdict
from market_rates.common import load,save
from market_rates.xlsx_read import read_xlsx,merged_ranges
from market_rates.board_plan import col,cell_number
from market_rates.board_batch_plan import label_tenor
from market_rates.amount_rows import amount_identity
from scripts.check_four_scope_fixes import blocks

def check(out):
    out=Path(out);p=load(out/'table-validation-plan.json');base=load(p['base_plan']);book=read_xlsx(p['report_output'],merge_anchors_only=True);merges=merged_ranges(p['report_output']);checks=[];views=[]
    def ck(name,actual,expected):
        if isinstance(expected,(float,int)):ok=isinstance(actual,(float,int)) and abs(actual-expected)<1e-10
        else:ok=actual==expected
        checks.append(dict(check=name,passed=ok));assert ok,(name,actual,expected)
    s=book['SGD挂牌']
    for bank,count in [('Maybank',4),('OCBC',6),('RHB',2),('SCB',5)]:
        spans=blocks(s,merges['SGD挂牌'],1,bank);ck(bank+' one block',len(spans),1);start,end=spans[0];ck(bank+' SGD bands',end-start+1,count)
        source=defaultdict(list)
        for q in base['details']:
            if q['bank']==bank and q['display_currency']=='SGD' and q['insertable']:
                key=(q['amount_max'],) if bank=='Maybank' else (q['amount_min'],q['amount_max'])
                source[key].append(q)
        ordered=sorted(source.values(),key=lambda rs:min(float(q['amount_min']) if q['amount_min'] is not None else -1 for q in rs))
        for row,rs in zip(range(start,end+1),ordered):
            for c in range(3,19):
                t=label_tenor(s.get(col(c)+'2'));rates=[float(q['rate_pct'])/100 for q in rs if str(q['tenor_value'])+q['tenor_unit']==t]
                ck(bank+' '+str(row)+' '+str(t),cell_number(s.get(col(c)+str(row))),max(rates) if rates else '-')
        views.append(dict(sheet='SGD挂牌',start=start,end=end,bank_col=1,current_col=3,last_col=19,name=bank.lower()+'-sgd-compact'))
    ck('Maybank active scope ordinary FX only',all(q['product_id'].startswith('maybank-fx-tier') for q in base['details'] if q['bank']=='Maybank' and q['currency']!='SGD'),True)
    for name,s in book.items():
        if not name.endswith('挂牌') or name=='SGD挂牌':continue
        bc=1 if name=='CNY挂牌' else 2
        for start,end in blocks(s,merges[name],bc,'Maybank'):
            labels=[str(s.get(col(bc+1)+str(r),'')) for r in range(start,end+1)]
            if not any(q['bank']=='Maybank' and q['display_currency']==name[:-2] for q in base['details']):
                ck('Maybank no unsupported quotes '+name,any(isinstance(cell_number(s.get(col(c)+str(r))),(int,float)) for r in range(start,end+1) for c in range(bc+2,14)),False)
                continue
            ck('Maybank ordinary labels '+name+str(start),all('外币定存挂牌' in x and 'isavvy' not in x.lower() for x in labels),True)
            if name=='USD挂牌' and not any(v['name']=='maybank-fx-ordinary' for v in views):
                views.append(dict(sheet=name,start=start,end=end,bank_col=2,current_col=4,last_col=6,name='maybank-fx-ordinary'))
    s=book['USD挂牌'];spans=blocks(s,merges['USD挂牌'],2,'SCB');ck('SCB board five displayed tenors',len(spans),5)
    for start,end in spans:
        ck('SCB USD four rows '+str(start),end-start+1,4)
        t=next(label_tenor(s.get('B'+str(r))) for r in range(start-1,0,-1) if label_tenor(s.get('B'+str(r))))
        for row,minimum in zip(range(start,end+1),['5000','100000','250000','500000']):
            rs=[q for q in base['details'] if q['bank']=='SCB' and q['currency']=='USD' and str(q['tenor_value'])+q['tenor_unit']==t and q['amount_min']==minimum]
            ck('SCB source rate '+t+' '+minimum,cell_number(s.get('D'+str(row))),float(rs[0]['rate_pct'])/100)
        if t=='6M':views.append(dict(sheet='USD挂牌',start=start,end=end,bank_col=2,current_col=4,last_col=6,name='scb-usd-board-compact'))
    s=book['USD促销'];allspans=blocks(s,merges['USD促销'],2,'SCB');six=[span for span in allspans if next(label_tenor(s.get('B'+str(r))) for r in range(span[0]-1,0,-1) if label_tenor(s.get('B'+str(r))))=='6M']
    ck('SCB single 6M promo block',len(six),1);start,end=six[0];ck('SCB three audiences',end-start+1,3)
    for r,value in zip(range(start,end+1),[.043,.044,.046]):
        ck('SCB promo current '+str(r),cell_number(s.get('D'+str(r))),value)
        ck('SCB promo prior '+str(r),cell_number(s.get('E'+str(r))),value)
    dc=next(re.match('[A-Z]+',a)[0] for a,v in s.items() if v=='当日增幅')
    ck('SCB daily change zero',cell_number(s.get(dc+str(start))),0)
    delta_col=0
    for letter in dc:delta_col=26*delta_col+ord(letter)-64
    views.append(dict(sheet='USD促销',start=start,end=end,bank_col=2,current_col=4,last_col=delta_col,compact_history=True,name='scb-usd-promo-compact'))
    s=book['SGD促销'];ocbc=blocks(s,merges['SGD促销'],1,'OCBC')
    six=[span for span in ocbc if '6M;' in str(s.get('B'+str(span[0])))]
    ck('OCBC one current 6M block',len(six),1);start,end=six[0];ck('OCBC no legacy duplicate 6M rows',end-start+1,2)
    ck('OCBC bank highest 6M',cell_number(s.get('C'+str(start))),.0135)
    ck('OCBC branch 6M retained in caption','1.30%' in str(s.get('B'+str(end))),True)
    views.append(dict(sheet='SGD促销',start=start,end=end,bank_col=1,current_col=3,last_col=4,name='ocbc-sgd-promo-compact'))
    save(out/'compact-layout-checks.json',dict(passed=True,count=len(checks),checks=checks))
    save(out/'compact-layout-previews.json',views);print('Seven requested repairs:',len(checks),'checks passed')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);check(a.parse_args().out)

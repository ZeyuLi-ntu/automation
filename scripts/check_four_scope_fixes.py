"""Saved Excel checks for the four user-requested customer/amount scope fixes."""
import argparse,re
from pathlib import Path
from market_rates.common import load,save
from market_rates.xlsx_read import read_xlsx,merged_ranges
from market_rates.board_plan import col,cell_number
from market_rates.board_batch_plan import label_tenor

def blocks(values,merges,bc,bank):
    result=[]
    for a,v in values.items():
        if v!=bank or not re.fullmatch(col(bc)+r'\d+',a):continue
        start=int(re.search(r'\d+',a)[0]);end=start
        for m in merges:
            if m.startswith(a+':'):end=int(re.search(r'\d+$',m)[0]);break
        result.append((start,end))
    return sorted(result)

def check(out):
    out=Path(out);p=load(out/'table-validation-plan.json');base=load(p['base_plan']);v=read_xlsx(p['report_output'],merge_anchors_only=True);ms=merged_ranges(p['report_output']);checks=[];previews=[]
    def ck(name,ok):
        checks.append(dict(check=name,passed=bool(ok)))
        assert ok,name
    name='SGD挂牌';s=v[name];spans=blocks(s,ms[name],1,'HLF');ck('HLF has one bank block',len(spans)==1);start,end=spans[0];ck('HLF exactly two rows',end-start+1==2)
    expected={1:(.0005,.00125),2:(.0005,.00125),3:(.001,.0015),4:(.001,.0015),5:(.001,.0015),6:(.0015,.002),7:(.0015,.002),8:(.0015,.002),9:(.002,.003),10:(.002,.003),11:(.002,.003),12:(.0025,.0035)}
    for c in range(3,19):
        t=label_tenor(s.get(col(c)+'2'))
        if t and t.endswith('M') and int(t[:-1]) in expected:
            for i,n in enumerate(expected[int(t[:-1])]):ck('HLF '+t+' '+str(i),abs(cell_number(s.get(col(c)+str(start+i)))-n)<1e-10)
    ck('HLF short-tenor minimum visible','10,000' in str(s.get('B'+str(start))))
    previews.append(dict(sheet=name,start=start,end=end,bank_col=1,current_col=3,last_col=19,name='hlf-two-bands'))
    for name,s in v.items():
        if not name.endswith('挂牌'):continue
        bc=1 if name in ['SGD挂牌','CNY挂牌'] else 2
        for start,end in blocks(s,ms[name],bc,'HSBC'):
            ck('No HSBC Premier board '+name+' '+str(start),not any(re.search('卓越|premier',str(s.get(col(bc+1)+str(r))),re.I) for r in range(start,end+1)))
    ck('Active board details contain no HSBC Premier',all(d['audience']=='personal' for d in base['details'] if d['bank']=='HSBC'))
    name='USD促销';s=v[name];hs=blocks(s,ms[name],2,'HSBC');ck('HSBC three promo tenor blocks',len(hs)==3)
    terms={3:.0375,6:.029,12:.0275}
    for start,end in hs:
        ck('HSBC Personal one row '+str(start),start==end)
        headings=[(r,label_tenor(s.get('B'+str(r)))) for r in range(1,start) if label_tenor(s.get('B'+str(r)))];t=headings[-1][1]
        ck('HSBC Personal '+t,abs(cell_number(s.get('D'+str(start)))-terms[int(t[:-1])])<1e-10)
        ck('HSBC row Personal label '+t,'personal' in str(s.get('C'+str(start))))
    previews.append(dict(sheet=name,start=hs[0][0],end=hs[0][1],bank_col=2,current_col=4,last_col=5,name='hsbc-personal-usd'))
    for cur in ['USD','CNY']:
        name=cur+'促销';s=v[name];bc=1 if cur=='CNY' else 2;cc=bc+2
        spans=blocks(s,ms[name],bc,'ICBC');ck('ICBC '+cur+' five tenors',len(spans)==5)
        for start,end in spans:
            ck('ICBC '+cur+' two bands '+str(start),end-start+1==2)
            threshold='50,000' if cur=='CNY' else '5,000'
            ck('ICBC '+cur+' threshold '+str(start),all(threshold in str(s.get(col(bc+1)+str(r))) for r in [start,end]))
            ck('ICBC '+cur+' counter minimum in note '+str(start),'20,000' in str(s.get(col(bc+1)+str(end))))
        previews.append(dict(sheet=name,start=spans[0][0],end=spans[0][1],bank_col=bc,current_col=cc,last_col=cc+1,name='icbc-'+cur.lower()+'-two-bands'))
    rb=read_xlsx(p['rainbow_output'],merge_anchors_only=True);cells=rb['USD Rate + Other Currency Rates']
    for bl in p['rainbow_blocks']:
        if bl['currency']!='USD':continue
        for g in bl['groups']:
            if g['bank']=='HSBC':
                ck('Rainbow HSBC '+bl['tenor'],len(g['rows'])==1 and abs(cell_number(cells.get(col(bl['col']+1)+str(g['target_row'])))-terms[int(bl['tenor'][:-1])])<1e-10)
    summary=v['最高报价汇总 '];row=next(int(a[1:]) for a,x in summary.items() if re.fullmatch(r'B\d+',a) and x=='HSBC' and 29<=int(a[1:])<=37)
    for c,t in [('D',3),('E',6),('G',12)]:ck('HSBC summary '+str(t),abs(cell_number(summary.get(c+str(row)))-terms[t])<1e-10)
    save(out/'four-scope-checks.json',dict(passed=True,count=len(checks),checks=checks));save(out/'four-scope-previews.json',previews);print('Four requested fixes checked:',len(checks))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);check(a.parse_args().out)

"""Reconcile row compaction against every retained historical observation."""
import argparse,re
from collections import Counter
from pathlib import Path
from market_rates.common import load,save
from market_rates.xlsx_read import read_xlsx,merged_ranges
from market_rates.board_plan import col,cell_number

DELTA_NAMES=['USD促销','CNY促销','其他外币促销利率','USD挂牌','CNY挂牌']
def equal(a,b):
    a,b=cell_number(a),cell_number(b)
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return abs(a-b)<1e-10
    return a==b or a in [None,''] and b in [None,'']

def check_deltas(path,values=None):
    values=values or read_xlsx(path,merge_anchors_only=True)
    forms=read_xlsx(path,formulas=True,merge_anchors_only=True);merges=merged_ranges(path);counts={}
    for name in DELTA_NAMES:
        s=values[name];bc=1 if name.startswith('CNY') else 2;cc=bc+2
        headers=[a for a,v in s.items() if v in ['当日增幅','当日最高报价变动']]
        assert headers,name+' missing change header'
        dc=re.match('[A-Z]+',headers[0])[0];count=0;seen=set();first_data=int(re.search(r'\d+',headers[0])[0])+1
        bank_spans=[]
        for m in merges[name]:
            match=re.fullmatch(col(bc)+r'(\d+):'+col(bc)+r'(\d+)',m)
            if match:bank_spans.append(tuple(map(int,match.groups())))
        for a,label in s.items():
            if not re.fullmatch(col(bc+1)+r'\d+',a) or not label or label in ['金额','全部公开报价','金额要求','日期']:continue
            row=int(re.search(r'\d+',a)[0]);bank=s.get(col(bc)+str(row))
            if row<first_data:continue
            if bank in ['银行','Bank'] or str(bank).startswith('Tenor:'):continue
            now=cell_number(s.get(col(cc)+str(row)));prev=cell_number(s.get(col(cc+1)+str(row)))
            numeric=lambda x:isinstance(x,(float,int)) and not isinstance(x,bool)
            if now!='-' and not numeric(now) and not numeric(prev):continue
            if '促销' in name:
                start,end=next(((x,y) for x,y in bank_spans if x<=row<=y),(row,row))
                if start in seen:continue
                seen.add(start)
                def best(c):
                    rs=[r for r in range(start,end+1) if numeric(cell_number(s.get(col(c)+str(r))))]
                    def is_personal(r):return bool(re.search(r'(?:/|；|\()\s*personal(?:\s|/|；|\)|$)|\bPersonal Banking\b',str(s.get(col(bc+1)+str(r),'')),re.I))
                    personal=[r for r in rs if is_personal(r)]
                    if any(is_personal(r) for r in range(start,end+1)):
                        rs=[r for r in rs if is_personal(r) or not re.search(r'\b(?:priority|premier|private|citigold|prestige)\b|卓越|私人|贵宾',str(s.get(col(bc+1)+str(r),'')),re.I)]
                    return max((cell_number(s.get(col(c)+str(r))) for r in personal or rs),default='-')
                now,prev=best(cc),best(cc+1);row=start
            addr=dc+str(row);f=forms[name].get(addr)
            assert isinstance(f,str) and f.startswith('='),(name,addr,'missing formula',f)
            if f!='=':
                for c in [cc,cc+1]:assert re.search(r'INDEX\(\d+:\d+,1,'+str(c)+r'\)',f),(name,addr,f)
            expected=round(now-prev,8) if numeric(now) and numeric(prev) else '-'
            assert equal(s.get(addr),expected),(name,addr,s.get(addr),expected)
            if expected==0:assert cell_number(s.get(addr))==0,(name,addr,'floating-point residual')
            count+=1
        assert count>0,name
        counts[name]=count
    return counts

def check(plan_path,output):
    p=load(plan_path);old=read_xlsx(p['report'],merge_anchors_only=True);new=read_xlsx(output,merge_anchors_only=True);saved_merges=merged_ranges(output);checks=0
    def test(name,a,b):
        nonlocal checks
        assert equal(a,b),(name,a,b)
        checks+=1
    for h in p['sheets']:
        name=h['sheet'];deleted=set(h['delete_rows']);shift=lambda r:r-sum(d<r for d in deleted)
        for m in h['bank_merges']:
            if m['end']>m['start']:
                address=col(h['bank_col'])+str(m['start'])+':'+col(h['bank_col'])+str(m['end'])
                assert address in saved_merges[name],(name,address,'missing bank merge')
        destinations={r:g['first'] for g in h['groups'] for r in g['rows']}
        updated={u['address'] for u in h['updates']};dc=set(h['delta_columns'])
        for u in h['updates']:test(name+'/'+u['final_address'],new[name].get(u['final_address']),u['expected'])
        for a,v in old[name].items():
            letters,n=re.fullmatch(r'([A-Z]+)(\d+)',a).groups();r=int(n)
            if r in h.get('excluded_rows',[]):continue
            if letters in dc or a in updated:continue
            dest=destinations.get(r,r)
            if r in deleted:
                c=0
                for ch in letters:c=c*26+ord(ch)-64
                if c<=h['current_col'] or not isinstance(cell_number(v),(int,float)):continue
            test(name+'/'+a,new[name].get(letters+str(shift(dest))),v)
    c=p['cimb_sgd'];deleted=set(c['delete_rows']);shift=lambda r:r-sum(d<r for d in deleted)
    changes={u['address']:u['expected'] for u in c['updates']};changes['B'+str(c['start'])]=c['label'];changes['S'+str(c['start'])]=c['note']
    for a,v in old['SGD挂牌'].items():
        letters,n=re.fullmatch(r'([A-Z]+)(\d+)',a).groups();r=int(n)
        if r in deleted:continue
        test('SGD/'+a,new['SGD挂牌'].get(letters+str(shift(r))),changes.get(a,v))
    touched={h['sheet'] for h in p['sheets']}|{'SGD挂牌'}
    if p.get('sgd_promo'):
        fix=p['sgd_promo'];deleted=set(fix['delete_rows']);changes={u['address']:u['expected'] for u in fix['updates']};shift=lambda r:r-sum(d<r for d in deleted)
        from market_rates.sgd_comparison import comparisons,check_saved
        changes.update({x['address']:x['expected'] for x in comparisons(old['SGD促销'],merged_ranges(p['report'])['SGD促销'])})
        for a,v in old['SGD促销'].items():
            letters,n=re.fullmatch(r'([A-Z]+)(\d+)',a).groups();r=int(n)
            if r not in deleted:test('SGD promo/'+a,new['SGD促销'].get(letters+str(shift(r))),changes.get(a,v))
        for a,value in changes.items():
            letters,n=re.fullmatch(r'([A-Z]+)(\d+)',a).groups();test('SGD split/'+a,new['SGD促销'].get(letters+str(shift(int(n)))),value)
        touched.add('SGD促销')
        check_saved(output,new)
    for name,s in old.items():
        if name in touched:continue
        dc={re.match('[A-Z]+',a)[0] for a,v in s.items() if v in ['当日增幅','当日最高报价变动']} if name in DELTA_NAMES else set()
        for a,v in s.items():
            if re.match('[A-Z]+',a)[0] not in dc:test(name+'/'+a,new[name].get(a),v)
    def errors(book):return Counter((name,v) for name,s in book.items() for v in s.values() if isinstance(v,str) and v.startswith(('#REF!','#VALUE!','#DIV/0!','#NAME?','#NUM!')))
    assert not errors(new)-errors(old),(errors(old),errors(new))
    result=dict(passed=True,checks=checks,delta_rows=check_deltas(output,new),removed={h['sheet']:len(h['delete_rows']) for h in p['sheets']},sgd_cimb_rows=2)
    save(Path(output).parent/'board-cleanup-checks.json',result);print(result);return result

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--plan',required=True);a.add_argument('--output',required=True);a.add_argument('--base-plan');x=a.parse_args();check(x.plan,x.output)
    if x.base_plan:
        base=load(x.base_plan);cleanup=load(x.plan);base['cleanup_parent_plan']=str(Path(x.base_plan).resolve());base['cleanup_plan']=str(Path(x.plan).resolve())
        base['output']=str(Path(x.output).resolve().parent);base['report_output']=str(Path(x.output).resolve())
        for h in base['histories']:
            fix=next(s for s in cleanup['sheets'] if s['sheet']==h['sheet']);h['max_row']-=len(fix['delete_rows'])
        for m in base['matrices']:
            if m['sheet']=='SGD挂牌':m['end']-=len(cleanup['cimb_sgd']['delete_rows'])
        save(Path(x.output).parent/'table-validation-plan.json',base)

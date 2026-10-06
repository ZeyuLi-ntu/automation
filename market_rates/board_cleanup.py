"""Compact duplicate board condition rows without discarding historic values."""
import re
from pathlib import Path
from collections import defaultdict
from .common import load,save
from .xlsx_read import read_xlsx,merged_ranges
from .board_plan import col,cell_number
from .board_batch_plan import label_tenor
from .amount_rows import amount_identity,same_amount

def number(v):return isinstance(cell_number(v),(float,int)) and not isinstance(v,bool)

def scb_audience(label):
    label=str(label or '').lower()
    if 'priority private banking' in label or '/ private' in label:return 'private'
    if 'priority banking' in label or '/ premier' in label:return 'premier'
    if 'personal banking' in label or '/ personal' in label:return 'personal'
    return None

def scb_low_band(label):
    a=amount_identity(label)
    return bool(a and a[0]=='range' and a[1] is not None and a[2] is not None and 5000<=a[1]<a[2]<=100000)
def plan(report,out):
    values=read_xlsx(report,merge_anchors_only=True);forms=read_xlsx(report,formulas=True,merge_anchors_only=True);merges=merged_ranges(report);sheets=[]
    for name,bc,cc in [('USD挂牌',2,4),('CNY挂牌',1,3),('USD促销',2,4),('CNY促销',1,3)]:
        if name not in values:continue
        s=values[name];f=forms[name];maxrow=max(int(re.search(r'\d+',a)[0]) for a,v in s.items() if v is not None)
        ds={re.match('[A-Z]+',a)[0] for a,v in s.items() if v in ['当日增幅','当日最高报价变动']}
        numeric_rows=defaultdict(list)
        for addr,v in s.items():
            letters,n=re.fullmatch(r'([A-Z]+)(\d+)',addr).groups();c=0
            for ch in letters:c=c*26+ord(ch)-64
            if c>=cc and letters not in ds and number(v):numeric_rows[int(n)].append((c,v))
        sections=[r for r in range(2,maxrow+1) if label_tenor(s.get(col(bc)+str(r),''))];groups=[];deletes=[];updates=[];conflicts=[];excluded=[]
        for si,start in enumerate(sections):
            end=sections[si+1]-1 if si+1<len(sections) else maxrow
            anchors=[r for r in range(start+2,end+1) if s.get(col(bc)+str(r)) and s.get(col(bc)+str(r)) not in ['银行','Bank']]
            if name=='USD促销':
                audience_rows=defaultdict(list)
                for ai,ar in enumerate(anchors):
                    if s.get(col(bc)+str(ar))!='SCB':continue
                    stop=anchors[ai+1]-1 if ai+1<len(anchors) else end
                    for row in range(ar,stop+1):
                        audience=scb_audience(s.get(col(bc+1)+str(row)))
                        if audience:audience_rows[audience].append(row)
                        elif not s.get(col(bc+1)+str(row)) and not numeric_rows[row]:excluded.append(row)
                for audience,cluster in audience_rows.items():
                    if len(cluster)<2:continue
                    dest=cluster[0];cells=defaultdict(list)
                    for row in cluster:
                        for c,v in numeric_rows[row]:cells[c].append((row,v))
                    if any(len({round(float(cell_number(v)),12) for _,v in vs})>1 for vs in cells.values()):raise ValueError('SCB promo histories disagree: '+audience)
                    for c,vs in cells.items():updates.append(dict(address=col(c)+str(dest),value=cell_number(vs[0][1]),expected=cell_number(vs[0][1]),sources=[col(c)+str(r) for r,_ in vs]))
                    deletes.extend(cluster[1:]);groups.append(dict(bank='SCB',first=dest,rows=cluster,label=s.get(col(bc+1)+str(dest))))
            for ai,ar in enumerate(anchors):
                stop=anchors[ai+1]-1 if ai+1<len(anchors) else end;bank=str(s[col(bc)+str(ar)]).strip();labels={r:str(s.get(col(bc+1)+str(r)) or '') for r in range(ar,stop+1)}
                if bank=='HSBC' and '挂牌' in name:
                    excluded += [r for r,label in labels.items() if re.search('premier|卓越',label,re.I)]
                if bank=='Maybank' and name=='USD挂牌':
                    # Retain only explicitly identified ordinary FX deposit
                    # tiers; old unlabelled/product-mixed rows stay in the input
                    # workbook archive, not in the current ordinary-rate table.
                    excluded += [r for r,label in labels.items() if label and ('外币定存挂牌' not in label or re.search('isavvy',label,re.I))]
                if '促销' in name:
                    keep=[]
                    if bank=='ICBC':
                        threshold='5' if name.startswith('USD') else '50'
                        keep=[r for r,label in labels.items() if re.search(r'(?:USD|RMB)\s*'+threshold+r'k',label,re.I)]
                        if len(keep)!=2:keep=[]
                    elif bank=='HSBC' and name.startswith('USD'):
                        keep=[r for r,label in labels.items() if re.search(r'USD\s*30\s*K',label,re.I)]
                        if len(keep)!=1:keep=[]
                    if keep:excluded += [r for r,label in labels.items() if r not in keep and label]
                    continue
                labels={r:label for r,label in labels.items() if r not in excluded}
                scb_low_equal=(bank=='SCB' and name=='USD挂牌' and len({round(float(cell_number(s.get(col(cc)+str(r)))),12) for r,label in labels.items() if scb_low_band(label) and number(s.get(col(cc)+str(r)))})==1)
                candidates=[v for v in labels.values() if '；' in v];clusters=[]
                for r,label in labels.items():
                    if not amount_identity(label,bank):continue
                    match=next((g for g in clusters if same_amount(labels[g[0]],label,bank,candidates) or (scb_low_equal and scb_low_band(labels[g[0]]) and scb_low_band(label))),None)
                    if match is None:clusters.append([r])
                    else:match.append(r)
                for cluster in clusters:
                    if len(cluster)<2:continue
                    dest=cluster[0];rowcells=defaultdict(list)
                    for r in cluster:
                        for c,v in numeric_rows[r]:rowcells[c].append((r,v))
                    # Differing historical observations cannot be silently merged.
                    clash=[c for c,items in rowcells.items() if c>cc and len({round(float(cell_number(v)),12) for _,v in items})>1]
                    if clash:conflicts.append(dict(bank=bank,rows=cluster,columns=clash));continue
                    for c,items in rowcells.items():
                        if c==cc:
                            personal=[x for x in items if 'personal' in labels[x[0]]];items=personal or items
                            src,v=max(items,key=lambda x:float(cell_number(x[1])))
                            formula=forms[name].get(col(c)+str(src));value=formula if isinstance(formula,str) and formula.startswith('=') and formula!='=' else cell_number(v)
                        else:src,v=items[0];value=cell_number(v)
                        updates.append(dict(address=col(c)+str(dest),value=value,expected=cell_number(v),sources=[col(c)+str(r) for r,_ in items]))
                    deletes.extend(cluster[1:]);groups.append(dict(bank=bank,first=dest,rows=cluster,label=labels[dest]))
        deletes=sorted(set(deletes+excluded));shift=lambda r:r-sum(d<r for d in deletes)
        for u in updates:
            letters,n=re.fullmatch(r'([A-Z]+)(\d+)',u['address']).groups();u['final_address']=letters+str(shift(int(n)))
        # Existing bank merged ranges shrink with row removal; reconstruct them.
        bank_merges=[]
        for addr in merges[name]:
            a,b=addr.split(':');letters,r=re.fullmatch(r'([A-Z]+)(\d+)',a).groups();endletters,z=re.fullmatch(r'([A-Z]+)(\d+)',b).groups()
            if letters==endletters==col(bc):
                retained=[n for n in range(int(r),int(z)+1) if n not in deletes]
                if retained:bank_merges.append(dict(original_start=int(r),start=shift(retained[0]),end=shift(retained[-1]),label=s.get(a)))
        # Deleted duplicate bank anchors may leave a second empty bank block.
        # Rebuild the surviving SCB spans from their retained condition rows.
        if name=='USD促销':
            bank_merges=[m for m in bank_merges if m['label']!='SCB']
            for si,start in enumerate(sections):
                end=sections[si+1]-1 if si+1<len(sections) else maxrow
                active=False;rs=[];orig=[]
                for r in range(start+2,end+1):
                    if s.get(col(bc)+str(r)):
                        active=s.get(col(bc)+str(r))=='SCB'
                        if active:orig.append(r)
                    if active and r not in deletes and scb_audience(s.get(col(bc+1)+str(r))):rs.append(r)
                if rs:
                    if [shift(r) for r in rs]!=list(range(shift(rs[0]),shift(rs[-1])+1)):raise ValueError('SCB retained promo bands must be adjacent')
                    bank_merges.append(dict(original_start=orig[0],start=shift(rs[0]),end=shift(rs[-1]),label='SCB'))
        sheets.append(dict(sheet=name,bank_col=bc,current_col=cc,delete_rows=deletes,excluded_rows=excluded,updates=updates,groups=groups,conflicts=conflicts,bank_merges=bank_merges,delta_columns=sorted(ds),old_max_row=maxrow))
    s=values['SGD挂牌'];start=next(int(a[1:]) for a,v in s.items() if a.startswith('A') and v=='CIMB');address=next(x for x in merges['SGD挂牌'] if x.startswith('A'+str(start)+':'));end=int(re.search(r'\d+$',address)[0])
    first=[]
    for c in range(3,19):
        addr=col(c)+str(start);third=col(c)+str(start+2);src=third if end-start+1>2 and number(s.get(third)) else addr;v=s.get(src,'-');fv=forms['SGD挂牌'].get(src,v)
        first.append(dict(address=addr,value=fv if isinstance(fv,str) and fv.startswith('=') and fv!='=' else cell_number(v),expected=cell_number(v)))
    promo=dict(delete_rows=[],updates=[],bank_merges=[])
    if 'SGD促销' in values:
        s=values['SGD促销'];f=forms['SGD促销']
        for m in merges['SGD促销']:
            if not re.fullmatch(r'A\d+:A\d+',m):continue
            a,b=m.split(':');startp,endp=int(a[1:]),int(b[1:])
            if s.get(a)!='OCBC':continue
            fresh=[r for r in range(startp,endp+1) if '定存促销 / personal' in str(s.get('B'+str(r)))]
            if len(fresh)!=2:continue
            for r in range(startp,endp+1):
                label=str(s.get('B'+str(r),''))
                if r in fresh or not re.search(r'1\.3(?:0|5)?%.*(?:branch|online)',label,re.I):continue
                if any(number(v) for a,v in s.items() if re.fullmatch(r'[A-Z]+'+str(r),a)):continue
                promo['delete_rows'].append(r)
            # Preserve SGD's existing merged bank-maximum formulas. The two
            # product captions retain their individual rates and conditions.
            promo['bank_merges'].append(dict(start=startp,end=endp,label='OCBC'))
        promo['delete_rows']=sorted(set(promo['delete_rows']))
    p=dict(report=str(Path(report).resolve()),output=str(Path(out).resolve()),sheets=sheets,sgd_promo=promo,cimb_sgd=dict(start=start,end=end,updates=first,delete_rows=list(range(start+2,end+1)),label='定期存款挂牌；SGD 低于100,000\n1–2M起存5,000；3M及以上起存1,000',note='同一金额档跨期限合并；仅保留普通定存，伊斯兰定存原始证据仍在明细。'))
    save(Path(out)/'board-cleanup-plan.json',p);return p

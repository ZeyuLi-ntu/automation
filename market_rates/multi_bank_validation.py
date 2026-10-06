"""Product-level partial template plan; never approves or publishes a quote."""
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import re
from .common import load, save
from .schema import FACTS, group_key,financial_terms
from .rules import build_views,build_updates
from .table_validation import sha, stable_blocks
from .xlsx_read import read_xlsx
from .workbook_policy import workbook_policy,included_groups,daily_change_cells,daily_change_formula,bank_blocks,bank_in_scope
from .weekly_history import column_mode,apply_overrides
from .workbook_policy import promo_reference_allowed

CORE=[f for f in FACTS if f!='conditions']
BASE={'RHB':'rhb-sgd-promo','CIMB':'cimb-sgd-online','HLF':'hlf-branch-promo','SCB':'scb-sgd-fresh-funds',
      'OCBC':'ocbc-sgd-promo','HLB':'hlb-sgd-promo','SBI':'sbi-sgd-promo',
      'UOB':'uob-sgd-promo','ICBC':'icbc-sgd-promo','BOC':'boc-sgd-mobile'}
BASE.update({'BEA':'bea-sgd-promo','CITI':'citi-sgd-promo','HSBC':'hsbc-sgd-promo',
    'SingFinance':'singfinance-sgd-online','Singapura Finance':'singapura-sgd-promo','Maybank':'maybank-sgd-standalone',
    'DBS':'dbs-sgd-promo','POSB':'posb-sgd-promo','MARI':'mari-sgd-promo','TRUST':'trust-sgd-promo'})

def core_signature(row):return tuple(row[f] for f in CORE)+(financial_terms(row),)

def matched_offers(run):
    """Refuse a whole group if either route has missing, duplicated or differing tiers."""
    from .manual_review import effective_offers
    accepted,blocked,_=effective_offers(run)
    return accepted,blocked

def raw_matched_offers(run):
    """Unmodified model-only agreement, for independent source scoring."""
    lanes={}
    for lane in ['llm','vlm']:
        groups=defaultdict(list)
        for r in run[lane]['offers']:groups[group_key(r)].append(r)
        lanes[lane]=groups
    good=[];bad=[]
    for group in sorted(set(lanes['llm'])|set(lanes['vlm'])):
        left,right=lanes['llm'][group],lanes['vlm'][group]
        ls=[core_signature(r) for r in left];rs=[core_signature(r) for r in right]
        if len(ls)!=len(set(ls)) or len(rs)!=len(set(rs)) or set(ls)!=set(rs):bad.append(group)
        else:good.extend(left)
    return good,bad

def plan_multi(run_folder,report,rainbow,inspection,output,approved=None):
    root=Path(run_folder);out=Path(output);run=load(root/'run.json');cfg=load(root/'config.snapshot.json');result=load(root/'result.json')
    if not run.get('pilot',{}).get('no_publication'):raise ValueError('Validation-only run required')
    benchmark=load(root/'benchmark.json')
    if (benchmark['evidence_hash']!=run['evidence_hash'] or benchmark.get('run_sha256')!=sha(root/'run.json')
        or set(benchmark['lanes'])!={'llm','vlm'}
        or any(v['matched']!=v['expected'] or v['unexpected'] for v in benchmark['lanes'].values())):
        raise ValueError('Pinned source qualification has unresolved core discrepancies')
    offers,blocked=matched_offers(run)
    if blocked:raise ValueError('Core disagreements must be reviewed before numeric insertion: '+str(blocked))
    policy=workbook_policy(cfg)
    # A reviewed source inventory can clear stale cells for unquoted banks to '-'.
    # No numeric rows come from this inventory; all offers still pass the strict gate above.
    missing_banks={c['bank'] for c in run.get('coverage',[]) if c.get('numeric_insertion') is False}
    base={b:p for b,p in BASE.items() if b in set(cfg['expected_banks'])|missing_banks and bank_in_scope(b,policy)}
    from .manual_review import effective_offers
    _,_,manual_receipts=effective_offers(run)
    from .weekly_history import identity
    current_edits={r['id'] for r in manual_receipts}
    current_edits.update(identity(r['offer']) for r in manual_receipts if r.get('offer'))
    untouched=[r for r in offers if identity(r) not in current_edits]
    inherited,manual_applied=apply_overrides(untouched,approved)
    inherited_by_key={identity(r):r for r in inherited}
    offers=[inherited_by_key.get(identity(r),r) for r in offers]
    deferred_tenors=set(policy.get('deferred_actual_tenors',[]))
    deferred_offers=[r for r in offers if f'{r["bank"]}/{r["product_id"]}/{r["tenor_value"]}{r["tenor_unit"]}' in deferred_tenors]
    presentation=[dict(r,reference_quote=promo_reference_allowed(r,run['as_of'],policy))
                  for r in offers if r not in deferred_offers]
    all_groups=build_views(presentation,cfg,{},run['as_of'],include_reference_quotes=True)['groups']
    groups=included_groups(all_groups,policy)
    unavailable=[u for u in build_updates(offers,{},cfg,run['as_of']) if u['main_pct'] is None and u['status'] in ['已停止提供','已过期','尚未生效']]
    snap=load(inspection);book=read_xlsx(report);sheet=book['SGD促销']
    shift=column_mode(run['as_of'],snap['baseline_date']) if snap.get('baseline_date') else 1
    blocks=[];tenor='1M';sections={}
    merges={int(m.split(':')[0][1:]):int(m.split(':')[1][1:]) for m in snap['merges'] if re.fullmatch(r'A\d+:A\d+',m)}
    for item in snap['report']:
        row=item['row'];name=item['values'][0]
        if isinstance(name,str):name=name.strip()
        if name=='Maribank':name='MARI'
        m=re.fullmatch(r'(\d+)\s*Months?',str(name),re.I)
        if m:
            if sections and tenor in sections:sections[tenor]['end']=row-1
            tenor=m[1]+'M';sections[tenor]=dict(start=row,end=max(x['row'] for x in snap['report']))
        if name in base:blocks.append(dict(bank=name,tenor=tenor,start=row,end=merges.get(row,row)))
    inputs=[]
    for g in groups:
        previous=next((v for v in (approved or {}).get('groups',[]) if v['id']==g['id']),None)
        g['human_reviewed']=bool(previous and {core_signature(v) for v in previous['details']}=={core_signature(v) for v in g['details']} and (approved or {}).get('bank_dates',{}).get(g['bank'])==run.get('bank_dates',{}).get(g['bank']))
        for r in g['details']:
            r['input_row']=len(inputs)+4;r['human_reviewed']=g['human_reviewed'];inputs.append(r)
        g['input_rows']=[r['input_row'] for r in g['details']]
    # Previously inserted products retain their own span inside one bank label.
    # Without these spans a weekly rerun would append the same product again.
    product_blocks=[]
    current_forms=read_xlsx(report,formulas=True,merge_anchors_only=True)['SGD促销']
    for b in blocks:
        # Newer complete workbooks have already inserted multiple products.
        # Resolve their actual input references, not stale approved row numbers.
        detected=[]
        for row in range(b['start'],b['end']+1):
            f=str(current_forms.get('C'+str(row),''));names=set()
            for quoted,bare,ir in re.findall(r"(?:'([^']+)'|([^=(),!]+))!\$?H\$?(\d+)",f):
                inputsheet=book.get(quoted or bare,{})
                if inputsheet.get('A'+ir)==b['bank']:names.add(inputsheet.get('B'+ir))
            candidates={g['product_id'] for g in groups if g['bank']==b['bank'] and g['display_tenor']==b['tenor'] and g['product_name'] in names}
            if len(candidates)>1:raise ValueError('Current quotation mixes different products')
            if candidates:
                product=next(iter(candidates))
                if not detected or detected[-1][1]!=product:detected.append((row,product))
        if detected:
            for n,(row,product) in enumerate(detected):
                product_blocks.append({**b,'product_id':product,'start':b['start'] if n==0 else row,'end':detected[n+1][0]-1 if n+1<len(detected) else b['end'],'bank_start':b['start'],'bank_end':b['end']})
            continue
        prior=sorted([g for g in (approved or {}).get('groups',[]) if g['bank']==b['bank'] and g['display_tenor']==b['tenor']],key=lambda g:g['report_row'])
        if len(prior)>1:
            for n,g in enumerate(prior):
                product_blocks.append({**b,'product_id':g['product_id'],'start':g['report_row'],'end':prior[n+1]['report_row']-1 if n+1<len(prior) else b['end'],'bank_start':b['start'],'bank_end':b['end']})
        else:product_blocks.append(dict(**b,product_id=base[b['bank']],bank_start=b['start'],bank_end=b['end']))
    updates=[];inserts=[];used=set()
    for b in product_blocks:
        matches=[g for g in groups if g['bank']==b['bank'] and g['display_tenor']==b['tenor'] and g['product_id']==b['product_id']]
        g=matches[0] if matches else None
        if g and g['id'] in used:raise ValueError('Ambiguous duplicate existing bank block')
        if g:
            extra=len(g['details'])-(b['end']-b['start']+1)
            if extra>0:inserts.append(dict(at=b['end']+1,count=extra,group=g,bank_start=b['bank_start'],bank_end=b['bank_end'],extension=True))
            used.add(g['id'])
        status=next((x['status'] for x in unavailable if x['bank']==b['bank'] and x['product_id']==b['product_id'] and x['display_tenor']==b['tenor']),None)
        updates.append(dict(**b,group=g,missing_status=status if g is None else None))
    for g in groups:
        if g['id'] in used:continue
        anchors=[b for b in blocks if b['bank']==g['bank'] and b['tenor']==g['display_tenor']]
        if not anchors and g['display_tenor'] in sections:
            # A newly offered tenor may lack this bank entirely in that section.
            # Add one bank block there; other tenors' bank blocks are not duplicated.
            inserts.append(dict(at=sections[g['display_tenor']]['end']+1,count=len(g['details']),group=g,bank_start=None,bank_end=None,new_bank=True))
            continue
        if len(anchors)!=1:raise ValueError('New product insertion boundary ambiguous: '+g['id'])
        inserts.append(dict(at=anchors[0]['end']+1,count=len(g['details']),group=g,bank_start=anchors[0]['start'],bank_end=anchors[0]['end']))
    # Combine simultaneous insertions so their relative order is deterministic.
    inserts.sort(key=lambda x:(x['at'],x['group']['product_id']))
    def moved(row):return row+sum(i['count'] for i in inserts if i['at']<=row)
    for u in updates:u.update(target_start=moved(u['start']),target_end=moved(u['end'])+sum(i['count'] for i in inserts if i.get('extension') and i['group']['id']==(u['group'] or {}).get('id')))
    for n,i in enumerate(inserts):i['target_start']=i['at']+sum(j['count'] for j in inserts[:n])
    bank_merges=[]
    for b in blocks:
        extra=[i for i in inserts if i['bank_start']==b['start']]
        if extra:bank_merges.append(dict(bank=b['bank'],start=moved(b['start']),end=moved(b['end'])+sum(i['count'] for i in extra)))
    for i in inserts:
        if i.get('new_bank'):bank_merges.append(dict(bank=i['group']['bank'],start=i['target_start'],end=i['target_start']+i['count']-1))
    for g in groups:
        record=next((u for u in updates if u['group'] and u['group']['id']==g['id']),None) or next(i for i in inserts if i['group']['id']==g['id'])
        g['report_row']=record['target_start']
    rainbow_groups=[]
    aliases={value:key for key,value in cfg.get('template_bank_aliases',{}).items() if key in base}
    if 'MARI' in base:aliases['Maribank']='MARI'
    for col,value in snap['rainbow'].items():
        prior=[]
        for n,values in enumerate(value['rows'],3):
            if values[0]:
                prior.append(dict(bank=aliases.get(str(values[0]).strip(),str(values[0]).strip()),prior_index=len(prior),source_start=n,rank_rate=values[1],rows=[]))
            if prior:prior[-1]['rows'].append(values)
        # Trim wholly empty tail; source blocks can have different heights.
        for b in prior:
            if not bank_in_scope(b['bank'],policy):continue
            while b['rows'] and all(v is None for v in b['rows'][-1]):b['rows'].pop()
        order={b['bank']:b['prior_index'] for b in prior}
        current=[g for g in groups if g['display_tenor']==value['title']]
        combined=[]
        for b in prior:
            if b['bank'] in base:
                if any(g['bank']==b['bank'] for g in current):continue
                b.update(rows=[[b['bank'],'-','本期未找到；未判定停止提供']],rank_rate='-1',source_start=None,missing=True)
                stopped=[u for u in unavailable if u['bank']==b['bank'] and u['display_tenor']==value['title']]
                if stopped:b['rows'][0][2]='；'.join(sorted({u['status'] for u in stopped}))+'（见人工处理记录或活动有效期）'
            elif not isinstance(b['rank_rate'],(int,float)):b['rank_rate']='-1'
            combined.append(b)
        for g in current:
            combined.append(dict(bank=g['bank'],prior_index=order.get(g['bank'],len(prior)),rank_rate=str(Decimal(g['main_pct'])/100),
                rows=[[g['bank'],None,None] for r in g['details']],group=g,source_start=None))
        ranked=bank_blocks(stable_blocks(combined));r=3
        for b in ranked:b['target_start']=r;r+=len(b['rows'])
        labels=[]
        for b in ranked:
            if labels and labels[-1]['bank']==b['bank']:labels[-1]['end']=b['target_start']+len(b['rows'])-1
            else:labels.append(dict(bank=b['bank'],start=b['target_start'],end=b['target_start']+len(b['rows'])-1))
        rainbow_groups.append(dict(col=int(col),tenor=value['title'],blocks=ranked,bank_labels=labels,last_row=r-1))
    summary=[]
    headers=snap['summary'][0]['values'][1:]
    for sr in snap['summary'][1:]:
        name=sr['values'][0]
        names=['DBS','POSB'] if name=='DBS/POSB' else ['MARI' if name=='Maribank' else name]
        if not any(b in base for b in names):continue
        for c,t in enumerate(headers,3):
            summary.append(dict(row=sr['row'],col=c,bank=name,tenor=t,
                input_rows=[r['input_row'] for g in groups if g['bank'] in names and g['display_tenor']==t for r in g['details']]))
    date_rows=[int(a[1:]) for a,v in sheet.items() if a.startswith('A') and a[1:].isdigit() and v=='日期']
    current=[a for a,v in sheet.items() if re.fullmatch(r'C\d+',a) and v is not None]
    deltas=[]
    for a in daily_change_cells(read_xlsx(report,formulas=True,merge_anchors_only=True)['SGD促销']):
        col,row=re.fullmatch(r'([A-Z]+)(\d+)',a).groups();ci=0
        for char in col:ci=ci*26+ord(char)-64
        target_row=moved(int(row))
        deltas.append(dict(source=a,row=target_row,col=ci+shift,formula=daily_change_formula(target_row)))
    plan=dict(mode='validation_only',as_of=run['as_of'],source_run=str(root.resolve()),source_pending=result['pending'],
        report_template=str(Path(report).resolve()),rainbow_template=str(Path(rainbow).resolve()),report_sha256=sha(report),rainbow_sha256=sha(rainbow),
        run_sha256=sha(root/'run.json'),result_sha256=sha(root/'result.json'),input_sheet='三行验证明细',details=inputs,groups=groups,
        report_updates=updates,report_inserts=inserts,bank_merges=bank_merges,deltas=deltas,workbook_policy=policy,
        deferred_groups=[g['id'] for g in all_groups if g not in groups],
        summary=summary,rainbow_groups=rainbow_groups,date_rows=date_rows,current_cells=current,
        source_urls=[p['url'] for p in run['pages']],report_original_rows=max(x['row'] for x in snap['report']),
        report_output=str((out/(run['as_of'].replace('-','')+'_三家银行验证_调研副本.xlsx')).resolve()),
        rainbow_output=str((out/(run['as_of'].replace('-','')+'_三家银行验证_彩虹表副本.xlsx')).resolve()))
    label=run.get('collection_label','三家银行验证')
    plan.update(collection_label=label,banks=list(base),bank_dates={b:d for b,d in run.get('bank_dates',{b:run['as_of'] for b in cfg['expected_banks']}).items() if bank_in_scope(b,policy)},coverage=[c for c in run.get('coverage',[]) if bank_in_scope(c['bank'],policy)],
                source_runs=run.get('source_runs',[]),bank_urls={b:[p['url'] for p in run['pages'] if p['bank']==b] for b in base})
    plan['input_sheet']='银行验证明细'
    template_sheets=set(book)|set(read_xlsx(rainbow))
    if plan['input_sheet'] in template_sheets:
        name='明细_'+run['as_of'].replace('-','');suffix=1
        while name in template_sheets:suffix+=1;name='明细_'+run['as_of'].replace('-','')+'_'+str(suffix)
        plan['input_sheet']=name
    plan.update(date_column_shift=shift,baseline_date=snap.get('baseline_date','2026-09-16'),
        history_action='insert_new_period' if shift else 'refresh_same_date',report_last_col=snap.get('report_last_col',242)+shift,
        style_row=snap.get('style_row',54),rainbow_original_last_row=snap.get('rainbow_last_row',44),
        approved_baseline_id=(approved or {}).get('id'),manual_applied=manual_applied,
        manual_notes=dict((approved or {}).get('manual_notes',{})),deferred_actual_tenors=list(deferred_tenors),
        deferred_tenor_offers=deferred_offers,manual_review_receipts=manual_receipts)
    for receipt in manual_receipts:
        if receipt.get('offer'):
            edited=receipt['offer']
            if edited['bank'] not in plan['bank_dates']:plan['bank_dates'][edited['bank']]=run['as_of']
            for r in inputs:
                if identity(r)==identity(edited):r['manual_reviewed']=True
            if receipt.get('source_url'):plan['bank_urls'][edited['bank']].append(receipt['source_url'])
        if receipt.get('note') and receipt.get('offer'):
            plan['manual_notes'][group_key(receipt['offer'])]=receipt['note']
    for kind,word in [('report','调研'),('rainbow','彩虹表')]:plan[kind+'_output']=str((out/(run['as_of'].replace('-','')+'_'+label+'_'+word+'.xlsx')).resolve())
    save(out/'table-validation-plan.json',plan);return plan

"""General bank-block plans: preserve source tiers and historical row semantics."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
from datetime import datetime,timedelta,timezone
import re
from .common import load,save,digest
from .xlsx_read import read_xlsx,merged_ranges
from .board_plan import col,tenor_label,cell_number,amount,formula,ROOT
from .board_batch_plan import label_tenor
from .manual_review import effective_offers
from .weekly_history import identity
from .workbook_policy import bank_in_scope,currency_in_scope,presentation_currency,board_rate_usable,workbook_policy,quote_in_scope
from .pipeline import check_evidence
from .table_validation import sha
from .rules import main_offer,active
from .board_wave import validate_wave
from .sheet_names import unused_sheet_name

def canonical_bank(bank):return 'DBS' if str(bank).strip() in ['DBS/POSB','POSB'] else str(bank).strip()
def collected_pairs(details):
    # Pilot collectors (including BOC) and wide collectors have the same
    # verified detail contract. Collector provenance must not suppress writing.
    return {(r['bank'],r['display_currency']) for r in details}
def tier_key(r):return tuple(str(r[k]) for k in ['product_id','audience','channel','amount_min','amount_max','min_inclusive','max_inclusive','amount_currency','amount_is_equivalent','conditions'])
def grouped(rows):
    groups={}
    for r in rows:groups.setdefault(tier_key(r),[]).append(r)
    return list(groups.values())

def matrix_groups(rows):
    if rows and rows[0]['bank'] in ['HLF','Singapura Finance'] and rows[0]['currency']=='SGD':
        # The source has two rate columns. Different tenor minimums belong in
        # their notes, rather than creating a third display row.
        out={}
        for r in rows:out.setdefault('low' if Decimal(r['amount_max'] or 0)==50000 else 'high',[]).append(r)
        return [out[k] for k in ['low','high'] if k in out]
    if rows and rows[0]['currency']=='SGD' and rows[0]['bank'] in ['Maybank','OCBC','RHB','SCB']:
        # Tenor-specific minimums and renewal terms do not create extra amount
        # columns on the source table. Retain those facts in each row's note.
        out={}
        for r in rows:
            if r.get('insertable') is False:continue
            key=(r['amount_max'],) if r['bank']=='Maybank' else (r['amount_min'],r['amount_max'])
            out.setdefault(key,[]).append(r)
        return sorted(out.values(),key=lambda rs:Decimal(min((r['amount_min'] for r in rs if r['amount_min'] is not None),key=Decimal,default='-1')))
    return grouped(rows)

def history_groups(rows):
    if rows and rows[0]['bank']=='SCB' and rows[0]['currency']=='USD':
        low=[r for r in rows if r['amount_min'] in ['5000','25000','50000'] and r['amount_max'] in ['24999','49999','99999']]
        if len(low)==3 and len({r['rate_pct'] for r in low})==1:
            return [low]+grouped([r for r in rows if r not in low])
    return grouped(rows)
def expected(rows):return float(Decimal(main_offer(rows)['rate_pct'])/100) if rows else '-'
def literal_or_formula(value):return value if isinstance(value,str) and value.startswith('=') else cell_number(value)
def make_cell(addr,rows,sheet):return dict(address=addr,formula=formula(rows,sheet),expected=float(max(Decimal(r['rate_pct']) for r in rows)/100) if rows else '-')

def plan(run_path,out,base):
    root=Path(run_path).resolve();run=load(root/'run.json');check_evidence(run,root/'evidence')
    for source in run['wide_sources']:validate_wave(source)
    offers,blocked,receipts=effective_offers(run)
    if blocked or not all(run[l]['coverage_complete'] for l in ['llm','vlm']):raise ValueError('Unresolved core disagreement')
    out=Path(out).resolve();sheet='挂牌全批_'+run['as_of'].replace('-','')+'_'+digest(run['id'])[:4]
    reviewed={identity(r['offer']) for r in receipts if r.get('offer')};details=[]
    events={(e['bank'],e['currency'],e['product_id']):e for e in run.get('source_date_events',[])}
    page_dates={p['id']:datetime.fromisoformat(p['captured_at']).astimezone(timezone(timedelta(hours=8))).date().isoformat() for p in run['pages'] if p.get('captured_at')}
    for r in sorted(offers,key=lambda r:(presentation_currency(r['currency']),r['bank'],r['product_id'],r['tenor_value'],Decimal(r['amount_min'] or '-1'))):
        if not bank_in_scope(r['bank']) or not currency_in_scope(r['currency']) or not quote_in_scope(r):continue
        reason=''
        if not board_rate_usable(r):reason='来源为特殊计息方式，保留明细'
        # ICBC explicitly quotes the USD "Below 100k" board tier. Display that
        # tier as printed; the nearby promotional minimum is a different offer.
        quoted_upper_tier=(r['bank']=='ICBC' and r['currency']=='USD' and r['product_id']=='icbc-usd-board' and r['amount_max']=='100000')
        if r['amount_min'] is None and not quoted_upper_tier and workbook_policy().get('board_missing_minimum')!='display_as_unspecified':reason=(reason+'；' if reason else '')+'起存门槛未列明'
        if r['currency']=='CHF':reason='现有模板无CHF区域，仅留明细'
        if r['bank']=='CIMB' and r['currency']!='SGD' and not (r['amount_min']==r['amount_max'] and r['min_inclusive'] and r['max_inclusive']):reason+='；金额列边界含义待核'
        if r['bank']=='RHB' and r['tenor_value'] in [1,2] and r['currency']=='SGD':reason='仅企业客户，本次个人挂牌不插表'
        if not active(r,run['as_of']):reason=(reason+'；' if reason else '')+('明确生效日期 '+str(r['valid_from'])+' 晚于本期' if r.get('valid_from') and r['valid_from']>run['as_of'] else '报价当前未生效或已停止')
        evidence_date=max([page_dates[e['page_id']] for e in r['evidence'] if e['page_id'] in page_dates],default=run['bank_dates'][r['bank']])
        source_dates=[m[0] for e in r['evidence'] if e['locator'].endswith('/source-date') for m in [re.findall(r'\d{4}-\d{2}-\d{2}',e['quote'])] if m]
        event=events.get((r['bank'],r['currency'],r['product_id']),{})
        date_note=('本次官网日期回退至 '+event['current_source_date']+'，保留上次较新报价 '+event['previous_source_date']) if event.get('retained_previous') else ''
        details.append(dict(r,input_row=len(details)+4,evidence_date=evidence_date,source_date=source_dates[0] if source_dates else None,date_status=event.get('status'),date_note=date_note,display_currency=presentation_currency(r['currency']),insertable=not reason,hold_reason=reason,manual_reviewed=identity(r) in reviewed))
    # Regeneration always starts from the same unchanged accepted base.
    replay=base.get('kind')=='board-wide' and Path(base['source_run']).resolve()==root
    report=base['report_template'] if replay else base['report_output']
    rainbow=base['rainbow_template'] if replay else base['rainbow_output']
    layout_base=base
    if base.get('inherited_board_plan'):layout_base=load(base['inherited_board_plan'])
    if replay:
        previous_plan=Path(base.get('base_output') or Path(report).parent)/'table-validation-plan.json'
        layout_base=load(previous_plan) if previous_plan.exists() else {}
        if layout_base and Path(layout_base['report_output']).resolve()!=Path(report).resolve():raise ValueError('Replay layout does not match its unchanged template')
    b=read_xlsx(report,merge_anchors_only=True);bf=read_xlsx(report,formulas=True,merge_anchors_only=True)
    rb=read_xlsx(rainbow,merge_anchors_only=True);rf=read_xlsx(rainbow,formulas=True,merge_anchors_only=True)
    sheet=unused_sheet_name(sheet,b,rb)
    newbanks={s['bank'] for p in run['wide_sources'] for s in load(Path(p)/'run.json')['sections']}
    target_pairs=collected_pairs(details)|{('HLB','CNY')}
    from .board_wave import SCB_FX,CIMB_FX
    for pending in run.get('coverage',[]):
        cur=pending.get('currency')
        if cur=='FX' and pending['bank'] in ['SCB','CIMB']:
            index=int(pending['section'].rsplit('-',1)[1]);cur=(SCB_FX if pending['bank']=='SCB' else CIMB_FX)[index]
        if cur and cur!='FX':target_pairs.add((pending['bank'],presentation_currency(cur)))
    select=lambda bank,cur,t=None,valid=False:[r for r in details if r['bank']==bank and r['display_currency']==cur and (t is None or str(r['tenor_value'])+r['tenor_unit']==t) and (not valid or r['insertable'])]
    def row_entry(rs,terms,startcol,source_row):
        d=rs[0];label=d['product_name']+'；'+amount(d)+'；'+d['audience']
        if d['currency']!=d['display_currency']:label+='；原币种 '+d['currency']
        if d['bank']=='HLF' and d['currency']=='SGD':
            label=('Board Rates；SGD ≤50,000' if Decimal(d['amount_max'] or 0)==50000 else 'Special Rates；SGD >50,000')
            label+='\n1–2M起存10,000；3M及以上起存500'
        if d['bank']=='Singapura Finance' and d['currency']=='SGD':
            label=('SGD <50,000' if Decimal(d['amount_max'] or 0)==50000 else 'SGD ≥50,000')
            label+='\n1–2M起存5,000；3M及以上起存500'
        if d['currency']=='SGD' and d['bank'] in ['Maybank','OCBC','RHB','SCB']:
            display=dict(d,amount_min=min((r['amount_min'] for r in rs if r['amount_min'] is not None),key=Decimal,default=None))
            label=amount(display).split('；')[0]
            if d['bank']=='Maybank':label+='\n1M起存10,000；36M仅续期'
            if d['bank']=='OCBC':label+='\n24M及以上仅同期限续期'
            if d['bank']=='SCB':label+='\n36M及以上仅同期限续期'
            if d['bank']=='RHB':label+='\n个人挂牌；1–2M仅企业，不列报价'
        note=d['conditions']+'；采集 '+d['evidence_date']+('；银行标注 '+d['source_date'] if d.get('source_date') else '')+('；生效 '+d['valid_from'] if d.get('valid_from') else '')+('；'+d['date_note'] if d.get('date_note') else '')+'；'+(d['hold_reason'] or '自动核验通过')
        values=[]
        for i,t in enumerate(terms):
            chosen=[r for r in rs if r['insertable'] and str(r['tenor_value'])+r['tenor_unit']==t];values.append(dict(col=startcol+i,formula=formula(chosen,sheet),expected=expected(chosen)))
        return dict(amount=label,note=note,values=values,source_row=source_row)
    matrices=[]
    for cur in ['SGD','AUD','NZD','CAD','HKD','EUR','GBP']:
        name=cur+'挂牌';s=b[name];f=bf[name];bc=1 if cur=='SGD' else 2;ac=bc+1;last=18 if cur=='SGD' else 13
        old_limit=max([m['end'] for m in layout_base.get('matrices',[]) if m['sheet']==name]+[99])
        anchors=[(row,canonical_bank(s[col(bc)+str(row)])) for row in range(3,old_limit+1) if s.get(col(bc)+str(row))]
        groups=[];inserts=[];end=max(row for row,_ in anchors)
        # The final bank's extent comes from its bank-cell merge.
        for address in merged_ranges(report)[name]:
            if address.startswith(col(bc)+str(end)+':'):end=max(end,int(re.search(r'\d+$',address)[0]))
        terms=[label_tenor(s.get(col(c)+'2','')) for c in range(ac+1,last+1)]
        for i,(start,bank) in enumerate(anchors):
            stop=anchors[i+1][0]-1 if i+1<len(anchors) else end
            if not bank_in_scope(bank):continue
            rows=[]
            if (bank,cur) in target_pairs:
                rows=[row_entry(rs,terms,ac+1,start) for rs in matrix_groups(select(bank,cur))]
            else:
                for row in range(start,stop+1):
                    rows.append(dict(source_row=row,amount=s.get(col(ac)+str(row),''),note=s.get(col(last+1)+str(row),''),values=[dict(col=c,formula=literal_or_formula(f.get(col(c)+str(row),'-')),expected=cell_number(s.get(col(c)+str(row),'-'))) for c in range(ac+1,last+1)]))
                if not select(bank,cur,valid=True):
                    for entry in rows:
                        entry['note']='本期未核实此银行/币种挂牌；待采集或适配'
                        for cell in entry['values']:cell.update(formula='-',expected='-')
            if not rows:rows=[dict(source_row=start,amount='本期待核',note='无已核实报价',values=[dict(col=c,formula='-',expected='-') for c in range(ac+1,last+1)])]
            if len(rows)>stop-start+1:inserts.append(dict(before=stop+1,count=len(rows)-(stop-start+1)))
            if bank not in ['HLF','HSBC','Maybank','OCBC','RHB','SCB','Singapura Finance']:
                while len(rows)<stop-start+1:rows.append(dict(source_row=start,amount='本期该旧档位未单列；见本银行明细',note='',values=[dict(col=c,formula='-',expected='-') for c in range(ac+1,last+1)]))
            groups.append(dict(bank=bank,label=s.get(col(bc)+str(start)),source_row=start,rows=rows,updated=(bank,cur) in target_pairs))
        target=3
        for g in groups:g['target_row']=target;target+=len(g['rows'])
        matrices.append(dict(sheet=name,currency=cur,bank_col=bc,amount_col=ac,last_col=last,note_col=last+1,start=3,old_end=end,end=max(end+sum(i['count'] for i in inserts),target-1),groups=groups,inserts=inserts))
    histories=[]
    for cur,bc,cc,oldmax in [('USD',2,4,248),('CNY',1,3,104)]:
        if layout_base.get('kind')=='board-wide':oldmax=next(h['max_row'] for h in layout_base['histories'] if h['currency']==cur)
        s=b[cur+'挂牌'];f=bf[cur+'挂牌'];sections=[(row,label_tenor(s[col(bc)+str(row)])) for row in range(1,oldmax+1) if col(bc)+str(row) in s and label_tenor(s[col(bc)+str(row)])]
        dateval=cell_number(s.get(col(cc)+str(sections[0][0]+1)));previous=(datetime(1899,12,30)+timedelta(days=float(dateval))).date().isoformat() if isinstance(dateval,(float,int)) else str(dateval)
        if previous>run['as_of']:raise ValueError('Out-of-order history')
        inserts=[];existing=[]
        for si,(start,t) in enumerate(sections):
            stop=sections[si+1][0]-1 if si+1<len(sections) else oldmax
            anchors=[(row,canonical_bank(s[col(bc)+str(row)])) for row in range(start+2,stop+1) if s.get(col(bc)+str(row))]
            for ai,(ar,bank) in enumerate(anchors):
                end=anchors[ai+1][0]-1 if ai+1<len(anchors) else stop
                # Do not absorb spacer rows beneath the last bank.
                while end>ar and s.get(col(bc+1)+str(end)) is None and s.get(col(cc)+str(end)) is None:end-=1
                if (bank,cur) in target_pairs:
                    rs=select(bank,cur,t);new=[]
                    current={row:dict(old_row=row,formula='-',expected='-',bank=bank) for row in range(ar,end+1)}
                    for group in history_groups(rs):
                        d=group[0];valid=[r for r in group if r['insertable']]
                        item=dict(formula=formula(valid,sheet),expected=expected(valid),amount=d['product_name']+'；'+amount(d)+'；'+d['audience']+('；原CNH，按CNY' if d['currency']=='CNH' else ''),note=d['conditions']+'；'+(d['hold_reason'] or '自动核验通过'))
                        if bank=='SCB' and cur=='USD' and len(group)==3:
                            item['amount']='定期存款挂牌；USD ≥5,000 且≤99,999；personal'
                        matched=[row for row in range(ar,end+1) if s.get(col(bc+1)+str(row))==item['amount']]
                        if len(matched)>1:raise ValueError('Duplicate historical condition rows')
                        if matched:current[matched[0]].update(formula=item['formula'],expected=item['expected'])
                        else:new.append(item)
                    if new:inserts.append(dict(before=end+1,anchor=ar,bank=bank,tenor=t,label=s[col(bc)+str(ar)],rows=new,count=len(new)))
                    existing+=list(current.values())
                elif bank in ['BOC','HLB','SBI']:
                    for row in range(ar,end+1):existing.append(dict(old_row=row,formula=literal_or_formula(f.get(col(cc)+str(row),'-')),expected=cell_number(s.get(col(cc)+str(row),'-')),bank=bank))
        shift=lambda row:row+sum(i['count'] for i in inserts if i['before']<=row)
        for i in inserts:i['target_row']=shift(i['before'])-i['count'];i['target_anchor']=shift(i['anchor'])
        for item in existing:item['address']=col(cc)+str(shift(item['old_row']))
        histories.append(dict(sheet=cur+'挂牌',currency=cur,bank_col=bc,current_col=cc,insert_date=previous!=run['as_of'],date_rows=[shift(r+1) for r,_ in sections],old_date_rows=[r+1 for r,_ in sections],old_max_row=oldmax,max_row=shift(oldmax),inserts=inserts,existing=existing,merges=merged_ranges(report)[cur+'挂牌']))
    rainbow_blocks=[]
    cny_title=next(row for row in range(50,300) if re.search(r'(?:CNY|RMB).*Board',str(rb['USD Rate + Other Currency Rates'].get('A'+str(row),'')),re.I))
    old_usd_end=cny_title-2
    old_sgd_end=max([x['end'] for x in layout_base.get('rainbow_blocks',[]) if x['currency']=='SGD']+[32])
    for name,cur,header,start,end,step in [('SGD Board Rate','SGD',2,3,old_sgd_end,3),('USD Rate + Other Currency Rates','USD',32,33,old_usd_end,4)]:
        s=rb[name];f=rf[name]
        for c in range(1,28,step):
            t=label_tenor(s.get(col(c)+str(header),''))
            if not t:continue
            gs=[];g=None
            for row in range(start,end+1):
                label=s.get(col(c)+str(row));rv=cell_number(s.get(col(c+1)+str(row)));av=s.get(col(c+2)+str(row))
                if label:
                    bank=canonical_bank(label);g=dict(bank=bank,label=str(label),source_row=row,order=len(gs),rows=[]);gs.append(g)
                if g and (label or rv is not None or av is not None):g['rows'].append(dict(source_row=row,formula=literal_or_formula(f.get(col(c+1)+str(row),'-')),expected=rv,amount=av or '',updated=False))
            gs=[g for g in gs if bank_in_scope(g['bank'])]
            for g in gs:
                if (g['bank'],cur) in target_pairs:
                    rs=select(g['bank'],cur,t);valid=[r for r in rs if r['insertable']];winner=main_offer(valid) if valid else None
                    ordered=([winner]+[r for r in rs if r is not winner]) if winner else rs
                    # All conditions remain in input details. Collapse only exact
                    # duplicates for display; different products stay separate.
                    g['rows']=[dict(source_row=g['source_row'],formula=formula([r] if r['insertable'] else [],sheet),expected=expected([r]) if r['insertable'] else '-',amount=r['product_name']+'；'+amount(r)+'；'+r['conditions']+'；'+(r['hold_reason'] or '自动核验通过'),updated=True) for r in ordered]
                    if not g['rows']:g['rows']=[dict(source_row=g['source_row'],formula='-',expected='-',amount='本期未核实此期限挂牌',updated=True)]
                else:
                    winner=None
                    if not select(g['bank'],cur,t,True):g['rows']=[dict(source_row=g['source_row'],formula='-',expected='-',amount='本期未核实此期限挂牌；见覆盖清单',updated=True)]
                nums=[r['expected'] for r in g['rows'] if isinstance(r['expected'],(int,float))];g['rank']=float(Decimal(str(expected([winner]))).quantize(Decimal('.000000000001'))) if winner else max(nums,default=-1)
            gs.sort(key=lambda g:(-g['rank'],g['order']));target=start
            for g in gs:g['target_row']=target;target+=len(g['rows'])
            rainbow_blocks.append(dict(sheet=name,currency=cur,col=c,tenor=t,start=start,end=max(end,target-1),groups=gs))
    rainbow_shift=max([x['end']-old_usd_end for x in rainbow_blocks if x['currency']=='USD']+[0]);rainbow_cells=[];summary=[]
    def put(target,addr,rows):target.append(make_cell(addr,rows,sheet))
    # Existing fixed-layout summaries: current highest quotation, all audiences.
    for cur,begin,end,bc,cols,terms in [('USD',43,55,2,3,['7D','1M','3M','6M','9M','12M','18M','24M']),('CNY',60,64,2,3,['1M','3M','6M','9M','12M','18M','24M'])]:
        for row in range(begin,end+1):
            bank=canonical_bank(b['最高报价汇总 '].get(col(bc)+str(row),''))
            for i,t in enumerate(terms):put(summary,col(cols+i)+str(row),select(bank,cur,t,True))
            from .board_batch_plan import winner_minimums
            available=select(bank,cur,valid=True);minimum=cur+' '+winner_minimums(available) if available else '-'
            for addr,value in [(('K' if cur=='USD' else 'J')+str(row),minimum),(('L' if cur=='USD' else 'K')+str(row),'本期核验；明细有来源日期' if available else '本期未核实')]:summary.append(dict(address=addr,formula=value,expected=value))
    for row in range(cny_title+2,cny_title+13):
        bank=canonical_bank(rb['USD Rate + Other Currency Rates'].get('A'+str(row),''));bank='HLB' if bank=='HL Bank' else bank
        if (bank,'CNY') not in target_pairs:continue
        for c,t in enumerate(['1M','3M','6M','9M','12M','18M','24M'],2):put(rainbow_cells,col(c)+str(row+rainbow_shift),select(bank,'CNY',t,True))
        if bank=='HLB':
            rainbow_cells += [dict(address='I'+str(row+rainbow_shift),formula='SGD 50,000 等值',expected='SGD 50,000 等值'),dict(address='J'+str(row+rainbow_shift),formula='原CNH，按用户规则归入CNY；用户已确认',expected='原CNH，按用户规则归入CNY；用户已确认')]
    # The CNY highest-rate section has a spare row immediately after its five
    # original banks. Add HLB there without displacing the following FX section.
    if b['最高报价汇总 '].get('B65') not in [None,'','HLB']:raise ValueError('CNY summary spare row occupied')
    summary += [dict(address='B65',formula='HLB',expected='HLB'),dict(address='J65',formula='SGD 50,000 等值',expected='SGD 50,000 等值'),dict(address='K65',formula='原CNH，按CNY使用',expected='原CNH，按CNY使用')]
    for i,t in enumerate(['1M','3M','6M','9M','12M','18M','24M'],3):put(summary,col(i)+'65',select('HLB','CNY',t,True))
    limitations=['原始采集、文字及视觉转录在本机完成。表格是复核副本，未自动批准历史。','CNH按CNY插表且保留原币种；JPY不进入采集任务、活动明细或本期数值。','挂牌数字按用户规则统一作为百分数使用，不因缺少%或p.a.留空；金额条件不明仍单独说明。银行报价日期与明确生效日期分别保留。','USD/CNY新增金额条件放在原银行区块内，旧金额行保留历史，本期旧档位填-；其他挂牌保持矩阵。','各报价保留实际证据日期；部分银行仍仅覆盖SGD。所有挂牌数字已由用户于2026-09-28确认按百分数使用；CIMB按官网金额报价点展示，不外推档位区间。']
    limitations += [c['bank']+' '+str(c.get('currency',''))+' '+c['reason'] for c in run.get('coverage',[])]
    p=dict(kind='board-wide',source_run=str(root),as_of=run['as_of'],bank_dates=run['bank_dates'],banks=sorted(run['bank_dates']),details=details,input_sheet=sheet,matrices=matrices,histories=histories,rainbow_blocks=rainbow_blocks,rainbow_shift=rainbow_shift,rainbow_cny_title=cny_title,rainbow_insert_before=old_usd_end+1,rainbow_cells=rainbow_cells,summary=summary,manual_receipts=receipts,limitations=limitations,evidence_hash=run['evidence_hash'],run_sha256=sha(root/'run.json'),new_banks=sorted(newbanks),base_output=base.get('output'),report_template=report,rainbow_template=rainbow,report_sha256=sha(report),rainbow_sha256=sha(rainbow),report_output=str(out/(run['as_of'].replace('-','')+'_挂牌全批_调研.xlsx')),rainbow_output=str(out/(run['as_of'].replace('-','')+'_挂牌全批_彩虹表.xlsx')))
    p['output']=str(out)
    if base.get('unified_predecessor'):p['unified_predecessor']=base['unified_predecessor']
    p['base_output']=str(Path(report).parent)
    out.mkdir(parents=True,exist_ok=False);save(out/'table-validation-plan.json',p);return p

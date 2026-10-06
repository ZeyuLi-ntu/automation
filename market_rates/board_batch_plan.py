"""Map verified source bands to existing board tables, retaining their history."""
from pathlib import Path
from decimal import Decimal
from collections import defaultdict
from datetime import datetime,timedelta
import re
from .common import load,save
from .table_validation import sha
from .xlsx_read import read_xlsx,merged_ranges
from .scope import bank_name
from .manual_review import effective_offers
from .pipeline import check_evidence
from .rules import active,main_offer
from .weekly_history import identity
from .board_plan import col,tenor_label,amount,formula,cell_number,ROOT
from .board_batch import bands
from .workbook_policy import board_rate_usable

def label_tenor(value):
    # Two existing CNY headings contain a trailing R. This is an exact legacy
    # label mapping, never a generalized fuzzy tenor match.
    return tenor_label({'Tenor: 3 monthR':'Tenor: 3 month','Tenor: 6 monthR':'Tenor: 6 month'}.get(str(value),value))

def interval_rows(rows,lower,upper):
    return [r for r in rows if r['amount_min'] is not None and Decimal(r['amount_min'])>=Decimal(lower)
            and (upper is None or Decimal(r['amount_min'])<Decimal(upper))
            and (upper is None or (r['amount_max'] is not None and Decimal(r['amount_max'])<=Decimal(upper)))]

def present_band(rows,sheet,description):
    # Presentation can collapse identical-rate tiers. If their rates differ,
    # splitting the template is required; do not silently use the maximum.
    if len({r['rate_pct'] for r in rows})>1:raise ValueError('Different rates inside one presentation band')
    return dict(formula=formula(rows,sheet),expected=float(Decimal(rows[0]['rate_pct'])/100) if rows else '-',amount=description)

def winner_minimums(rows):
    grouped=defaultdict(list)
    for r in rows:grouped[str(r['tenor_value'])+r['tenor_unit']].append(r)
    result=defaultdict(list);unspecified=[]
    for t,rs in grouped.items():
        high=max(Decimal(r['rate_pct']) for r in rs);eligible=[r for r in rs if Decimal(r['rate_pct'])==high]
        if any(r['amount_min'] is None for r in eligible):unspecified.append(t);continue
        minimum=min(Decimal(r['amount_min']) for r in eligible)
        result[format(minimum,',f')].append(t)
    suffix=('；'+('/'.join(unspecified))+'官网未列起存') if unspecified else ''
    if not result:return '官网未列起存门槛'
    if len(result)==1:return '≥'+next(iter(result))+suffix
    baseline=max(result,key=lambda v:Decimal(v.replace(',','')))
    return '≥'+baseline+'\n'+'；'.join('/'.join(ts)+'可低至'+v for v,ts in result.items() if v!=baseline)+suffix

def plan(run_path,out,base):
    root=Path(run_path).resolve();run=load(root/'run.json');check_evidence(run,root/'evidence')
    for parent in run.get('parents',[]):
        parent=Path(parent);source=load(parent/'run.json')
        if not source.get('packets'):continue
        proof=load(parent/'currency-checks.json')
        if proof['evidence_hash']!=source['evidence_hash'] or not proof['passed'] or len(proof['checks'])!=len(source['packets']) or any(not c['passed'] for c in proof['checks']):raise ValueError('Incomplete screenshot currency verification')
    checks=load(root/'dom-checks.json')
    pairs={(p['bank'],p['currency'],lane) for p in run['pages'] for lane in ['llm','vlm']}
    if {(c['bank'],c['currency'],c['lane']) for c in checks if c['passed']}!=pairs or not all(c['passed'] for c in checks):raise ValueError('Incomplete literal table verification')
    offers,blocked,receipts=effective_offers(run)
    if blocked:raise ValueError('Core disagreement: '+str(blocked))
    if not all(run[l]['coverage_complete'] for l in ['llm','vlm']):raise ValueError('Incomplete dual coverage')
    reviewed={identity(r['offer']) for r in receipts if r.get('offer') and not r.get('carried_forward')}
    sheet='挂牌批次_'+run['as_of'].replace('-','');details=[]
    for i,r in enumerate(sorted(offers,key=lambda r:(r['currency'],r['bank'],r['tenor_value'],Decimal(r['amount_min'] or '-1'),r['channel'])),4):
        reason=''
        if r['currency'] in ['CNH','JPY']:reason='模板无独立'+r['currency']+'区域，仅留明细'
        elif r['amount_min'] is None:reason='起存门槛未列明，仅留明细'
        elif not board_rate_usable(r):reason='来源为特殊计息方式，保留明细'
        elif not active(r,run['as_of']):reason='不在有效期内'
        details.append(dict(r,input_row=i,insertable=not reason,hold_reason=reason,manual_reviewed=identity(r) in reviewed))
    valid=[r for r in details if r['insertable']]
    if base.get('kind')=='board-batch':report,rainbow=base['report_template'],base['rainbow_template']
    else:report,rainbow=base['report_output'],base['rainbow_output']
    b=read_xlsx(report,merge_anchors_only=True);rb=read_xlsx(rainbow,merge_anchors_only=True);rf=read_xlsx(rainbow,formulas=True,merge_anchors_only=True);merges=merged_ranges(report)
    select=lambda bank,currency,t:[r for r in valid if r['bank']==bank and r['currency']==currency and str(r['tenor_value'])+r['tenor_unit']==t]
    def source_bands(cur):
        p=next(p for p in run['pages'] if p['id']=='boc-'+cur.lower()+'-rates')
        return [(str(lo),str(hi) if hi is not None else None,row[1]) for row in p['grid'][2:] for lo,hi in [bands(row[1])]]
    def description(cur,lo,hi,rows):
        if not rows:return cur+' '+('≥'+lo if hi is None else lo+' 至 <'+hi)+'；低于起存门槛'
        if cur=='SGD' and Decimal(lo)==0:return 'SGD <20,000；在线≥500；分行≥5,000'
        return cur+' ≥'+format(Decimal(rows[0]['amount_min']),',f')+(' 且<'+format(Decimal(hi),',f') if hi else '')+('；分行/在线' if cur=='SGD' else '')
    report_cells=[];matrices=[];histories=[];summary=[]
    def put(target,addr,value,expected=None,**kw):target.append(dict(address=addr,formula=value,expected=value if expected is None else expected,**kw))
    for cur in ['SGD','AUD','NZD','CAD','HKD','EUR','GBP']:
        name=cur+'挂牌';s=b[name];bc=1 if cur=='SGD' else 2;ac=bc+1;last=18 if cur=='SGD' else 13;note=last+1
        targets=['BOC']+(['HLB'] if cur in ['AUD','NZD','GBP','HKD'] else [])
        for bank in targets:
            anchors=[r for r in range(3,90) if bank_name(s.get(col(bc)+str(r),''))==bank]
            if len(anchors)!=1:raise ValueError('Matrix bank anchor ambiguous '+name+bank)
            start=anchors[0];specs=source_bands(cur) if bank=='BOC' else [(None,None,None)]
            for off,(lo,hi,rawlabel) in enumerate(specs):
                row=start+off
                if off and s.get(col(bc)+str(row)):raise ValueError('New bank would be overwritten')
                allrows=[r for r in valid if r['bank']==bank and r['currency']==cur]
                group=interval_rows(allrows,lo,hi) if bank=='BOC' else allrows
                desc=description(cur,lo,hi,group) if bank=='BOC' else amount(group[0]) if group else '起存门槛待核；只留明细'
                cells=[]
                for c in range(ac+1,last+1):
                    t=label_tenor(s.get(col(c)+'2',''));rs=[r for r in group if str(r['tenor_value'])+r['tenor_unit']==t]
                    v=present_band(rs,sheet,desc);put(cells,col(c)+str(row),v['formula'],v['expected'])
                matrices.append(dict(sheet=name,bank=bank,row=row,amount_col=ac,note_col=note,amount=desc,cells=cells,note='证据 '+run['as_of']+'；待复核'+('；该档低于起存门槛' if bank=='BOC' and not group else '')))
    usd_specs=[('2000','50000'),('50000','500000'),('500000',None)]
    for cur,bc,ac,current in [('USD',2,3,4),('CNY',1,2,3)]:
        s=b[cur+'挂牌'];dates=[];sections=[]
        for row in range(1,260 if cur=='USD' else 105):
            t=label_tenor(s.get(col(bc)+str(row),''))
            if t:sections.append((row,t));dates.append(row+1)
        if len(dates)!=(8 if cur=='USD' else 5):raise ValueError('History sections changed')
        dateval=s.get(col(current)+str(dates[0]));serial=cell_number(dateval)
        previous=(datetime(1899,12,30)+timedelta(days=float(serial))).date().isoformat() if isinstance(serial,(float,int)) else str(dateval)
        if previous>run['as_of']:raise ValueError('Refuse out-of-order history')
        insert=previous!=run['as_of'];cells=[]
        for i,(start,t) in enumerate(sections):
            end=sections[i+1][0]-1 if i+1<len(sections) else (248 if cur=='USD' else 104)
            anchors=[r for r in range(start+2,end+1) if bank_name(s.get(col(bc)+str(r),''))=='BOC']
            if len(anchors)!=1:raise ValueError('History BOC anchor missing')
            anchor=anchors[0];specs=usd_specs if cur=='USD' else [(lo,hi) for lo,hi,_ in source_bands(cur)]
            for off,(lo,hi) in enumerate(specs):
                rows=interval_rows(select('BOC',cur,t),lo,hi);v=present_band(rows,sheet,'')
                put(cells,col(current)+str(anchor+off),v['formula'],v['expected'],bank='BOC',tenor=t)
        histories.append(dict(sheet=cur+'挂牌',currency=cur,current_col=current,insert=insert,date_rows=dates,sections=[x[0] for x in sections],max_row=248 if cur=='USD' else 104,cells=cells,merges=merges[cur+'挂牌']))
    for cur,row,start,terms in [('USD',43,3,['7D','1M','3M','6M','9M','12M','18M','24M']),('CNY',60,3,['1M','3M','6M','9M','12M','18M','24M'])]:
        for i,t in enumerate(terms):
            rows=select('BOC',cur,t);put(summary,col(start+i)+str(row),formula(rows,sheet),float(Decimal(main_offer(rows)['rate_pct'])/100) if rows else '-')
    # CNY current date has only BOC coverage: other banks cannot retain old quotes
    # in the newly dated summary. Their historical source columns stay intact.
    for row in range(61,65):
        for c in range(3,10):put(summary,col(c)+str(row),'-')
    rainbow_blocks=[]
    for name,cur,header,start,end,step in [('SGD Board Rate','SGD',2,3,28,3),('USD Rate + Other Currency Rates','USD',32,33,64,4)]:
        cells=rb[name]
        for c in range(1,28,step):
            t=label_tenor(cells.get(col(c)+str(header),''))
            if not t:continue
            groups=[];g=None
            for row in range(start,end+1):
                label=cells.get(col(c)+str(row));rv=cell_number(cells.get(col(c+1)+str(row)));av=cells.get(col(c+2)+str(row))
                if label:g=dict(bank=bank_name(label),label=str(label),original_row=row,order=len(groups),rows=[]);groups.append(g)
                if g and (label or rv is not None or av is not None):g['rows'].append(dict(source_row=row,formula=rf[name].get(col(c+1)+str(row)) if str(rf[name].get(col(c+1)+str(row),'')).startswith('=') else rv,expected=rv,amount=av or '',updated=False))
            for g in groups:
                if g['bank']=='BOC':
                    specs=source_bands(cur) if cur=='SGD' else [(lo,hi,'') for lo,hi in usd_specs];new=[]
                    for lo,hi,_ in specs:
                        rows=interval_rows(select('BOC',cur,t),lo,hi)
                        if rows:new.append(dict(source_row=g['original_row'],**present_band(rows,sheet,description(cur,lo,hi,rows)+'；待复核'),updated=True))
                    g['rows']=new or [dict(source_row=g['original_row'],formula='-',expected='-',amount='本期无此期限公开挂牌报价',updated=True)]
                nums=[Decimal(str(r['expected'])) for r in g['rows'] if isinstance(r['expected'],(int,float))];g['rank']=float(max(nums).quantize(Decimal('0.000000000001'))) if nums else -1
                if g['bank']=='BOC':g['rows'].sort(key=lambda r: -r['expected'] if isinstance(r['expected'],(int,float)) else 1)
            groups.sort(key=lambda g:(-g['rank'],g['order']));target=start
            for g in groups:g['target_row']=target;target+=len(g['rows'])
            rainbow_blocks.append(dict(sheet=name,currency=cur,col=c,start=start,end=max(end,target-1),tenor=t,groups=groups))
    shift=max([b['end']-64 for b in rainbow_blocks if b['currency']=='USD']+[0]);rainbow_cells=[]
    for row in range(68,79):
        for c,t in enumerate(['1M','3M','6M','9M','12M','18M','24M'],2):
            rs=select('BOC','CNY',t) if row==68 else []
            put(rainbow_cells,col(c)+str(row+shift),formula(rs,sheet),float(Decimal(main_offer(rs)['rate_pct'])/100) if rs else '-')
    usd_min='USD '+winner_minimums([r for r in valid if r['bank']=='BOC' and r['currency']=='USD'])
    cny_min='CNY '+winner_minimums([r for r in valid if r['bank']=='BOC' and r['currency']=='CNY'])
    put(rainbow_cells,'I'+str(68+shift),cny_min);put(rainbow_cells,'J'+str(68+shift),'本期BOC；待复核')
    put(rainbow_cells,'J'+str(74+shift),'CNH独立保留明细，不代入CNY')
    for cur,start in [('AUD',2),('NZD',5),('GBP',11)]:
        for off,t in enumerate(['1M','3M','6M']):
            rs=select('HLB',cur,t);put(rainbow_cells,col(start+off)+str(88+shift),formula(rs,sheet),float(Decimal(main_offer(rs)['rate_pct'])/100) if rs else '-')
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    p=dict(kind='board-batch',mode='validation_only',source_run=str(root),as_of=run['as_of'],bank_dates=run['bank_dates'],banks=sorted(run['bank_dates']),input_sheet=sheet,details=details,
        report_template=report,rainbow_template=rainbow,report_sha256=sha(report),rainbow_sha256=sha(rainbow),report_output=str(out/(run['as_of'].replace('-','')+'_挂牌扩展_调研.xlsx')),rainbow_output=str(out/(run['as_of'].replace('-','')+'_挂牌扩展_彩虹表.xlsx')),
        matrices=matrices,histories=histories,summary=summary,usd_minimum=usd_min,cny_minimum=cny_min,rainbow_blocks=rainbow_blocks,rainbow_shift=shift,rainbow_cells=rainbow_cells,manual_receipts=receipts,evidence_hash=run['evidence_hash'],run_sha256=sha(root/'run.json'),
        limitations=['本批为BOC多币种、HLB新增外币挂牌，合并已确认HLB/SBI SGD/USD；其他银行仍为历史资料，不能视为全市场最新排名','HLB HKD缺少币种专属起存门槛；CNH和JPY没有独立模板区域，仅保留明细','原金额档位仅在利率完全相同且条件能明确表达时合并展示，完整档位和渠道保留输入明细','USD同日更新当前列；CNY新增日期列，未采集银行本期填-；旧日期列保持不变','新结果待人工复核，不自动批准历史；SBI USD单位已按用户确认处理'])
    save(out/'table-validation-plan.json',p);return p

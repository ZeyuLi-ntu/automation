"""Fail-closed, template-preserving mappings for the HLB/SBI board pilot."""
from pathlib import Path
from decimal import Decimal
import re
from .common import load,save
from .table_validation import sha
from .xlsx_read import read_xlsx
from .scope import bank_name
from .manual_review import effective_offers
from .pipeline import check_evidence
from .rules import active,main_offer
from .weekly_history import identity
from .workbook_policy import board_rate_usable

ROOT=Path(__file__).resolve().parents[1]
BANKS={'HLB','SBI'}
def col(n):
    s=''
    while n:n,k=divmod(n-1,26);s=chr(65+k)+s
    return s
def tenor_label(text):
    text=str(text).replace('Tenor:','').strip()
    m=re.fullmatch(r'(\d+)\s*(M|D|months?|days?)',text,re.I)
    return str(int(m[1]))+('M' if m[2].lower().startswith('m') else 'D') if m else None
def amount(r):
    x=r['amount_currency']+(' 等值 ' if r['amount_is_equivalent'] else ' ')
    if r['amount_min'] is None and r['amount_max'] is not None:
        return x+('≤' if r['max_inclusive'] else '<')+format(Decimal(r['amount_max']),',f')+'；起存未另列；渠道原文未列明'
    x+=('≥' if r['min_inclusive'] else '>')+format(Decimal(r['amount_min']),',f') if r['amount_min'] is not None else '官网未列起存金额'
    if r['amount_max'] is not None:x+=(' 且≤' if r['max_inclusive'] else ' 且<')+format(Decimal(r['amount_max']),',f')
    return x+'；'+{'online':'在线','branch':'分行','unknown':'渠道原文未列明'}.get(r['channel'],r['channel'])
def formula(rows,sheet):return '=MAX('+','.join("'"+sheet+"'!I"+str(r['input_row']) for r in rows)+')' if rows else '-'
def cell_number(value):
    if isinstance(value,str) and re.fullmatch(r'-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?',value):return float(value)
    return value

def make_plan(run_path,out,base=None):
    root=Path(run_path).resolve();out=Path(out).resolve();run=load(root/'run.json');check_evidence(run,root/'evidence')
    checks=load(root/'dom-checks.json')
    if len(checks)!=8 or not all(c['passed'] for c in checks):raise ValueError('Missing independent table checks')
    offers,blocked,receipts=effective_offers(run)
    if blocked:raise ValueError('Resolve all core disagreements before insertion: '+str(blocked))
    if any(r['bank'] not in BANKS or r['currency'] not in ['SGD','USD'] or r['rate_type']!='board' for r in offers):raise ValueError('Outside pilot scope')
    if base is None:base=load(Path(load(ROOT/'outputs/latest-workflow.json')['output'])/'table-validation-plan.json')
    sheet='挂牌输入_'+run['as_of'].replace('-','')
    details=[]
    reviewed={identity(r['offer']) for r in receipts if r.get('offer') and not r.get('carried_forward')}
    for i,r in enumerate(sorted(offers,key=lambda r:(r['currency'],r['bank'],r['tenor_value'],r['channel'])),4):
        details.append(dict(r,input_row=i,insertable=active(r,run['as_of']) and board_rate_usable(r),manual_reviewed=identity(r) in reviewed))
    valid=[r for r in details if r['insertable']]
    report=base.get('report_template') if base.get('kind')=='board-pilot' else base['report_output']
    rainbow=base.get('rainbow_template') if base.get('kind')=='board-pilot' else base['rainbow_output']
    b=read_xlsx(report,merge_anchors_only=True);rb=read_xlsx(rainbow,merge_anchors_only=True)
    def select(bank,currency,t,channel=None):
        rows=[r for r in valid if r['bank']==bank and r['currency']==currency and str(r['tenor_value'])+r['tenor_unit']==t and (channel is None or r['channel']==channel)]
        return rows
    # Existing single-row bank anchors are verified before any native Excel edit.
    s=b['SGD挂牌'];anchors={bank:next((i for i in range(3,80) if bank_name(s.get('A'+str(i),''))==bank),None) for bank in BANKS}
    if anchors!={'SBI':26,'HLB':48}:raise ValueError('SGD template layout changed; remap before writing')
    matrix=[]
    for bank,row,ch in [('SBI',26,None),('HLB',48,'online'),('HLB',49,'branch')]:
        chosen=[r for r in details if r['bank']==bank and r['currency']=='SGD' and (ch is None or r['channel']==ch)]
        if not chosen:raise ValueError('Missing SGD condition tier')
        item=dict(bank=bank,row=row,amount=amount(chosen[0]),cells=[])
        for c in range(3,19):
            t=tenor_label(s.get(col(c)+'2',''));rows=select(bank,'SGD',t,ch)
            item['cells'].append(dict(address=col(c)+str(row),formula=formula(rows,sheet),expected=float(Decimal(main_offer(rows)['rate_pct'])/100) if rows else '-'))
        item['note']='证据 '+run['as_of']+'；'+amount(chosen[0])+'；待人工复核'
        if bank=='SBI':item['note']+='；8天至不足1月及>24至60月区间保留原文，未展开插表'
        matrix.append(item)
    usd=b['USD挂牌'];usd_rows=[];date_rows=[];tenor=None;bank=None
    for i in range(1,249):
        v=usd.get('B'+str(i));t=tenor_label(v)
        if t:tenor=t;date_rows.append(i+1);bank=None;continue
        if v and bank_name(v) in BANKS:bank=bank_name(v)
        elif v:bank=None
        if bank in BANKS and i not in date_rows and (usd.get('C'+str(i)) is not None or usd.get('D'+str(i)) is not None):
            rows=select(bank,'USD',tenor);all_rows=[r for r in details if r['bank']==bank and r['currency']=='USD' and str(r['tenor_value'])+r['tenor_unit']==tenor]
            usd_rows.append(dict(bank=bank,row=i,tenor=tenor,formula=formula(rows,sheet),expected=float(Decimal(main_offer(rows)['rate_pct'])/100) if rows else '-',amount=amount(all_rows[0]) if all_rows else '-',note='年化单位未明确，暂不插入数值' if all_rows and not rows else '证据 '+run['as_of']+'；待人工复核'))
    if len(usd_rows)!=10 or len(date_rows)!=8:raise ValueError('USD history layout changed')
    rainbow_blocks=[]
    for name,currency,header,start,end,step in [('SGD Board Rate','SGD',2,3,27,3),('USD Rate + Other Currency Rates','USD',32,33,64,4)]:
        cells=rb[name]
        for c in range(1,28,step):
            t=tenor_label(cells.get(col(c)+str(header),''))
            if not t:continue
            groups=[];group=None
            for row in range(start,end+1):
                nameval=cells.get(col(c)+str(row));rv=cell_number(cells.get(col(c+1)+str(row)));av=cells.get(col(c+2)+str(row))
                if nameval:
                    group=dict(bank=bank_name(nameval),label=str(nameval),original_row=row,rows=[],order=len(groups));groups.append(group)
                if group and (nameval or rv is not None or av is not None):group['rows'].append(dict(source_row=row,formula=rv,expected=rv,amount=av or '',updated=False))
            for g in groups:
                if g['bank'] in BANKS:
                    selected=select(g['bank'],currency,t)
                    if selected:
                        winner=main_offer(selected);ordered=[winner]+[r for r in selected if r is not winner]
                        g['rows']=[dict(source_row=g['original_row'],formula=formula([r],sheet),expected=float(Decimal(r['rate_pct'])/100),amount=amount(r)+'；'+run['as_of']+' 待复核',updated=True) for r in ordered]
                    else:g['rows']=[dict(source_row=g['original_row'],formula='-',expected='-',amount='本期未核实/单位待核；见挂牌输入',updated=True)]
                nums=[Decimal(str(r['expected'])) for r in g['rows'] if isinstance(r['expected'],(int,float))]
                g['rank']=float(max(nums).quantize(Decimal('0.000000000001'))) if nums else -1
            groups.sort(key=lambda g:(-g['rank'],g['order']))
            target=start
            for g in groups:
                g['target_row']=target;target+=len(g['rows'])
            if currency=='USD' and target>end+1:raise ValueError('USD rainbow group overflow')
            rainbow_blocks.append(dict(sheet=name,currency=currency,col=c,start=start,end=max(end,target-1),tenor=t,groups=groups))
    report_out=out/(run['as_of'].replace('-','')+'_挂牌试点_调研.xlsx');rainbow_out=out/(run['as_of'].replace('-','')+'_挂牌试点_彩虹表.xlsx')
    pending_units=sorted({r['bank']+'/'+r['currency'] for r in details if not board_rate_usable(r)})
    p=dict(kind='board-pilot',mode='validation_only',source_run=str(root),as_of=run['as_of'],bank_dates=run['bank_dates'],banks=sorted(BANKS),input_sheet=sheet,details=details,pending_units=pending_units,
        report_template=report,rainbow_template=rainbow,report_sha256=sha(report),rainbow_sha256=sha(rainbow),report_output=str(report_out),rainbow_output=str(rainbow_out),
        matrix=matrix,usd_rows=usd_rows,usd_date_rows=date_rows,rainbow_blocks=rainbow_blocks,manual_receipts=receipts,
        limitations=['仅HLB/SBI；未采集银行不能代表本期市场排名']+([', '.join(pending_units)+'原表未明确年化单位，数值保留明细，不进入年利率表'] if pending_units else [])+['SBI区间期限及USD 2M本轮仅保留明细，未新增期限组','未人工处理的结果仍待核实；不自动登记历史'],
        evidence_hash=run['evidence_hash'],run_sha256=sha(root/'run.json'))
    out.mkdir(parents=True,exist_ok=False);save(out/'table-validation-plan.json',p);return p

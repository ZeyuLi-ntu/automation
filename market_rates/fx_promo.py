"""Foreign-currency promotions from checked literal tables. No remote model calls."""
import re
from datetime import datetime
from decimal import Decimal
from .schema import normalize
from .workbook_policy import presentation_currency

def numeric(text):
    m=re.search(r'[+-]?\d[\d,]*(?:\.\d+)?',text)
    if not m:raise ValueError('Missing numeric value: '+text)
    return str(Decimal(m[0].replace(',','')))

def tenor(text):
    n=int(numeric(text))
    return (n*12,'M') if 'year' in text.lower() else (n*7,'D') if 'week' in text.lower() else (n,'M')

def promotion_dates(s):
    if s['bank']=='BOC':
        for e in s.get('extra_evidence',[]):
            if '本次个人定期存款促销利率有效期' in e['quote']:
                dates=re.findall(r'(20\d{2})年(\d{1,2})月(\d{1,2})日',e['quote'])
                if len(dates)==2:return tuple(datetime(int(y),int(m),int(d)).date().isoformat() for y,m,d in dates)
        raise ValueError('Missing BOC ordinary promotion validity')
    pattern=r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d{2})\b'
    if s['bank'] in ['BEA','ICBC','SBI']:return None,None
    quotes=sorted(s.get('extra_evidence',[]),key=lambda e:'terms' not in e['page_id'])
    for e in quotes:
        q=e['quote'];compact=re.sub(r'\s+',' ',q)
        if not (re.search(r'promot',q,re.I) and re.search(r'valid from|available from|commences on|begins',compact,re.I)):continue
        matches=re.findall(pattern,q,re.I);dates=[]
        for d,m,y in matches:
            dates.append(datetime.strptime(f'{d} {m[:3]} {y}','%d %b %Y').date().isoformat())
        if dates:return dates[0],dates[1] if len(dates)>1 else None
    if s['bank']=='CITI' and s['layout'].endswith('new-funds'):
        for e in quotes:
            m=re.search(r'ends\s+'+pattern,e['quote'],re.I)
            if m:return None,datetime.strptime(f'{m[1]} {m[2][:3]} {m[3]}','%d %b %Y').date().isoformat()
    raise ValueError('Promotion validity must be read from current evidence: '+s['id'])

def normalize_fx(s,board=()):
    bank=s['bank'];layout=s['layout'];grid=s['rows'];out=[]
    evidence=[e for e in s.get('extra_evidence',[]) if e['quote'].strip()]
    def add(cur,label,value,lo=None,hi=None,*,audience='personal',channel='未列明',name='外币定存促销',fresh='unknown',conditions='',start=None,end=None,amount_cur=None,equivalent=False,ui=True,product=None,extra=None):
        if cur=='JPY':return
        n,u=tenor(label);r=dict(bank=bank,product_id=product or s['product_id'],product_name=name,currency=cur,rate_type='promo',tenor_value=n,tenor_unit=u,audience=audience,channel=channel,amount_min=str(lo) if lo is not None else None,amount_max=str(hi) if hi is not None else None,min_inclusive=True,max_inclusive=ui if hi is not None else False,amount_currency=amount_cur or cur,amount_is_equivalent=equivalent,fresh_funds=fresh,conditions=conditions or '按官网公布的外币定存条件',rate_pct=numeric(value),rate_basis='annual_nominal',valid_from=start,valid_to=end,availability='available',evidence=[dict(page_id=s['page_id'],quote=' | '.join([cur,label,value]),locator=s['id'])]+evidence+(extra or []))
        if s.get('source_date'):r['evidence'].append(dict(page_id=s['page_id'],quote='银行标注日期 '+s['source_date'],locator=s['id']+'/source-date'))
        if r['fresh_funds']=='required':r['fresh_funds']='yes'
        out.append(normalize(r));return out[-1]
    if bank=='BOC':
        names={'美元':'USD','澳元':'AUD','新西兰元':'NZD','欧元':'EUR','英镑':'GBP','人民币':'CNY'};cur=None;term=None;lo=None
        for physical in grid:
            row=list(physical)
            if row[0] in names:cur=names[row.pop(0)];lo=None
            if cur is None:continue
            if '个月' in row[0]:term=int(numeric(row.pop(0)))
            if len(row)==2:lo=numeric(row.pop(0))
            if len(row)!=1 or lo is None:raise ValueError('BOC merged-cell state changed')
            add(cur,str(term)+' months',row[0],lo,channel='手机银行',name='手机银行普通促销',product='boc-fx-mobile',conditions='普通新存单；须已有活期账户；非新客户产品')
        for r in out:
            higher=[x for x in out if x['currency']==r['currency'] and x['tenor_value']==r['tenor_value'] and Decimal(x['amount_min'])>Decimal(r['amount_min'])]
            if higher:r['amount_max']=min(higher,key=lambda x:Decimal(x['amount_min']))['amount_min'];r['max_inclusive']=False
    elif bank=='BEA':
        for row in grid[2:]:
            if len(row)!=9:raise ValueError('BEA tier shape changed')
            for label,value in zip(grid[1][1:],row[3:]):
                add(row[1],label,value,numeric(row[2]),name='Tier Rates',conditions='官网Tier Rates，沿用原调研分类；达到SGD500,000等值须另询银行，不能直接套用本表')
    elif bank=='CIMB':
        for row in grid[2:]:
            for label,value in zip(grid[1],row[1:]):add(row[0],label,value,10000,1000000,channel='在线CIMB Clicks',start='2026-09-01',end='2026-09-30',conditions='须有对应外币活期/储蓄账户；个人或联名；到期按挂牌续存')
    elif bank=='RHB':
        for row in grid[1:]:
            for label,value in zip(grid[0][1:4],row[1:4]):add(row[0],label,value,numeric(row[4]),start='2026-08-03',conditions='个人客户；新存及符合条件的到期续存；新旧资金均可')
    elif bank=='SBI':
        row=grid[1];add('USD',row[1],row[2],numeric(row[3]),1000000,ui=False,channel='柜台/客户经理',conditions='新存和续存均可；每名客户同币种存款合计必须小于1,000,000，不是每笔额度')
    elif bank=='SCB':
        row=grid[1];rates=re.findall(r'(Personal Banking|Priority Private Banking|Priority Banking)\s*:\s*([\d.]+)%',row[2])
        if len(rates)!=3:raise ValueError('SCB customer rows changed')
        for label,value in rates:add('USD',row[0],value,numeric(row[1]),audience={'Personal Banking':'personal','Priority Banking':'premier','Priority Private Banking':'private'}[label],channel='网银/手机',fresh='required',start='2026-09-01',end='2026-09-30',conditions=label+'；外部新资金，不含30天内提取再存；优惠须持有至到期')
    elif bank=='ICBC':
        cur=s['currency'];terms=grid[0][1:] if cur=='CNY' else [r[0] for r in grid[2:]]
        bands=[(500,50000),(50000,None)] if cur=='CNY' else [(500,5000),(5000,None)]
        for bi,(lo,hi) in enumerate(bands):
            for ti,label in enumerate(terms):
                value=grid[bi+1][ti+1] if cur=='CNY' else grid[ti+2][bi+1]
                counter=hi is None or hi>20000
                add(cur,label,value,lo,hi,ui=False,channel='电子银行/柜台' if counter else '电子银行',conditions='电子银行500起存；'+('柜台20,000起存；金额档位以本表上下界为准' if counter else '本档仅适用电子银行，柜台20,000起存'))
    elif bank=='HSBC':
        if s['currency']=='USD':
            aud=layout.split('-')[-1];audiences={'elite':'premier_elite','wealth':'premier_wealth','premier':'premier_standard','personal':'personal'}
            for row in grid[1:]:add('USD',row[0],row[1],30000,audience=audiences[aud],channel='分行/客户经理/电话/邮件',fresh='required',start='2026-09-01',end='2026-09-30',conditions='USD30,000新资金；本行为非App渠道公布报价；App实际报价以确认页为准'+('；须满足财富持有或指定外汇交易资格' if aud=='wealth' else ''))
        else:add(s['currency'],'3 months',grid[0][0],30000,channel='手机/分行',fresh='required',start='2026-09-01',end='2026-09-30',conditions='对应币种30,000新资金；3个月；App报价以提交时确认为准')
    elif bank=='CITI':
        if layout.endswith('conversion'):
            for row in grid[1:]:add(row[0],'1 month',row[1],50000,5000000,amount_cur='USD',equivalent=True,channel='Treasury Sales Officer/客户顾问',name='换汇定存促销',start='2026-09-01',end='2026-09-30',conditions='必须从另一币种换汇并通过客户顾问办理，非网银/App；须有Citi活期或储蓄账户；新旧资金均可；上限为每名主客户总额度')
        elif layout.endswith('new-funds'):
            row=grid[1]
            for label,value in zip(grid[0][1:],row[1:]):add('USD',label,value,5000,5000000,fresh='required',name='新资金定存促销',end='2026-09-30',conditions='现有Citi客户须带入新资金；新客户须先建立Citigold/Private Client财富关系；详细新资金认定以官网条款为准')
    elif bank=='DBS':
        for row in grid[1:]:
            n,u=tenor(row[0]);bonus=Decimal(numeric(row[1]));candidates=[r for r in board if r['bank']=='DBS' and r['currency']=='USD' and r['tenor_value']==n and r['tenor_unit']==u]
            if not candidates:raise ValueError('DBS verified current board dependency missing')
            for r in candidates:
                lo=max(Decimal(r['amount_min'] or 0),Decimal(10000));hi=min(Decimal(r['amount_max'] or 500000),Decimal(500000));ui=r['max_inclusive'] if r['amount_max'] is not None and Decimal(r['amount_max'])<=500000 else True
                if lo>hi or (lo==hi and not ui):continue
                add('USD',row[0],str(Decimal(r['rate_pct'])+bonus),lo,hi,ui=ui,channel='digibank网银/手机',start='2026-08-01',end='2026-09-30',name='挂牌加点促销',conditions=f"现有DBS/POSB个人客户；当期挂牌{r['rate_pct']}%＋加点{bonus}%；优惠码{row[3]}（区分大小写）；每笔10,000–500,000，可多笔",extra=r['evidence'])
    else:raise ValueError('Unsupported FX adapter '+bank)
    start,end=promotion_dates(s)
    for r in out:r['valid_from']=start;r['valid_to']=end
    return out

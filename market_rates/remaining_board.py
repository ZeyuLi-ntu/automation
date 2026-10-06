"""Deterministic mapping of the remaining banks' original board tables."""
import re
from decimal import Decimal
from .schema import normalize

def normalize_remaining(s,lane):
    from .board_wave import amount_band,number,tenor_values
    records=[];layout=s['layout'];cur=s['currency'];rows=s['rows']
    def add(label,band,value,*,minimum=None,maximum=None,min_inclusive=True,max_inclusive=False,note='',product=None):
        if str(value).strip().lower() in {'','-','–','—','n/a','n.a.','none'}:return
        term=re.sub(r'(?<=\d)-(?=[a-zA-Z])','',str(label)).replace('*','').strip()
        parsed=tenor_values(term,plain_month=layout=='cimb-sgd')
        if re.fullmatch(r'\d+\s*days?',term,re.I):parsed=[(int(re.match(r'\d+',term)[0]),'D')]
        if not parsed:raise ValueError('Unparsed board tenor: '+label)
        for n,u in parsed:
            lo,hi,li,ui=amount_band(band) if band else (None,None,True,False)
            if minimum is not None:lo=str(minimum);li=min_inclusive
            if maximum is not None:hi=str(maximum);ui=max_inclusive
            extra=note
            if layout=='dbs-fx' and u=='D':
                # Literal zeros remain in the archived table. The explicit
                # footnote limits which short-tenor placements are offered.
                if n==1 and cur not in {'USD','GBP','EUR'}:continue
                limit=500000 if cur=='HKD' else 100000 if cur in {'AUD','CAD','NZD'} else 50000
                lo=str(max(Decimal(lo or '0'),Decimal(limit)))
                if hi and (Decimal(lo)>Decimal(hi) or (Decimal(lo)==Decimal(hi) and not ui)):continue
            if layout=='uob-fx':
                limit=200000 if cur=='HKD' else 250000 if cur in {'CNH','CNY'} else 25000 if u=='D' else 5000
                lo=str(max(Decimal(lo or '0'),Decimal(limit)))
                if hi and (Decimal(lo)>Decimal(hi) or (Decimal(lo)==Decimal(hi) and not ui)):continue
                extra+='；月期/周期起存门槛按官网脚注分别处理'
            if layout=='cimb-sgd' and n<3:lo=str(max(Decimal(lo or '0'),Decimal(5000)))
            evidence=[dict(page_id=s['page_id'],quote=' | '.join([cur,str(band),str(label),str(value)]),locator=s['id']+'/'+lane)]+s.get('extra_evidence',[])
            if s.get('source_date'):evidence.append(dict(page_id=s['page_id'],quote='银行标注日期 '+s['source_date'],locator=s['id']+'/source-date'))
            records.append(normalize(dict(bank=s['bank'],product_id=s['product_id'],product_name=product or '定期存款挂牌',currency=cur,rate_type='board',tenor_value=n,tenor_unit=u,
                audience='personal',channel='unknown',amount_min=lo,amount_max=hi,min_inclusive=li,max_inclusive=ui,amount_currency=cur,amount_is_equivalent=False,
                fresh_funds='unknown',conditions='挂牌；'+str(band)+('；'+extra if extra else ''),rate_pct=number(value),rate_basis='annual_nominal' if layout!='dbs-fx' else 'unknown',
                valid_from=s.get('valid_from'),valid_to=None,availability='available',evidence=evidence)))
    if layout=='dbs-fx':
        previous=None
        for row in rows[1:]:
            if len(row)!=len(rows[0]):raise ValueError('DBS grid width changed')
            upper=Decimal(re.sub(r"[^0-9.]",'',row[0]));inclusive=row[0].startswith('<=')
            if previous is not None and upper<=previous:raise ValueError('DBS amount ceilings not ascending')
            for label,value in zip(rows[0][1:],row[1:]):
                add(label,row[0].replace("'",','),value,minimum=previous,maximum=upper,max_inclusive=inclusive,
                    note='官网金额上限依序分档；另须达到SGD5,000等值；周存期另有币种门槛，隔夜仅指定币种，见原文条款')
            previous=upper
    elif layout=='uob-fx':
        for row in rows[2:]:
            if len(row)!=len(rows[0]):raise ValueError('UOB grid width changed')
            for term,value in zip(rows[0][1:],row[1:]):add(term,row[0],value)
    elif layout=='rhb-fx':
        band=s['band'];minimum=None;maximum=None
        if band.startswith('Up to'):maximum='99999';band='<=99,999'
        for term,value in zip(rows[0][1:],rows[1][1:]):add(term,band,value,maximum=maximum,max_inclusive=True,note='按官网金额档位；起存门槛未另列' if minimum is None and maximum else '')
    elif layout=='sbi-fx':
        for row in rows[3:]:
            if len(row)!=2:raise ValueError('SBI board row changed')
            add(row[0],rows[1][0],row[1],note='官网目前仍公布的挂牌；生效日不要求等于采集日')
    elif layout=='cimb-sgd':
        for row in rows[1:]:
            if len(row)!=len(rows[0]):raise ValueError('CIMB board columns changed')
            for band,value in zip(rows[0][1:],row[1:]):
                band=re.sub(r'^Board Rates.*?\n','',band,flags=re.S)
                add(row[0],band,value,note='1及2个月最低S$5,000',product='伊斯兰定存挂牌' if s['islamic'] else '定期存款挂牌')
    elif layout=='hlb-hkd':
        for row in rows[1:]:add(row[0],'',row[1],note='官网公布港币挂牌；HKD专属起存门槛未列明，不外推其他币种门槛')
    else:raise ValueError(layout)
    return records

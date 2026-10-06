"""Normalize only the verified OCBC board layouts and their explicit conditions."""
import re
from .schema import normalize


def normalize_ocbc_section(s, lane):
    from .board_wave import amount_band, number, tenor_values
    rows=s['rows']; fx=s['layout']=='ocbc-fx'; cur=s['currency']; result=[]
    if s.get('rate_basis')!='annual_nominal' or not s.get('basis_evidence'):
        raise ValueError('OCBC linked interest/eligibility evidence is required')
    if fx:
        if rows[0][0]!='Time Deposit Amt' or rows[0][-1]!='Value Date':raise ValueError('OCBC FX headers changed')
        terms=rows[0][1:-1]
        if [tenor_values(t) for t in terms]!=[[(n,'M')] for n in [1,2,3,5,6,7,8,9,12]]:raise ValueError('Unexpected OCBC FX tenors')
        if cur not in {'USD','AUD','NZD','CAD','HKD','EUR','GBP'}:raise ValueError('OCBC currency outside requested Bank List')
        if s.get('minimum')!=('50000' if cur=='HKD' else '5000'):raise ValueError('OCBC linked minimum missing')
    elif 'Tenure' not in rows[0][0]:raise ValueError('OCBC SGD header changed')
    for row in rows[1:]:
        if len(row)!=len(rows[0]):raise ValueError('OCBC amount/tenor column mismatch')
        cells=zip(terms,row[1:-1]) if fx else zip(rows[0][1:],row[1:])
        for axis,value in cells:
            if value.strip().lower() in {'n.a','n.a.','n/a','-','–','—',''}:continue
            label=axis if fx else row[0]; band=row[0] if fx else axis
            if fx and band.startswith('First $'):
                lo,hi,li,ui=s['minimum'],re.sub(r'[^0-9.]','',band),True,True
            else:
                lo,hi,li,ui=amount_band(band)
                if fx and band.startswith('Above '):li=False
            if lo is None:raise ValueError('OCBC minimum unresolved')
            parsed=tenor_values(label,plain_month=not fx)
            if not parsed:raise ValueError('OCBC unparsed tenure: '+label)
            for n,u in parsed:
                note='挂牌；'+band
                if fx:note+='；仅网上存入，分行报价可能不同；Value Date为起息日'
                if not fx and n>=24:note+='；仅同期限旧存款续期，不接受新存入'
                quote=' | '.join([cur,band,label,value]+(['Value Date '+row[-1]] if fx else []))
                r=dict(bank='OCBC',product_id=s['product_id'],product_name='网上外币定存挂牌' if fx else '定期存款挂牌',currency=cur,rate_type='board',tenor_value=n,tenor_unit=u,
                    audience='personal',channel='online' if fx else 'unknown',amount_min=lo,amount_max=hi,min_inclusive=li,max_inclusive=ui,
                    amount_currency=cur,amount_is_equivalent=False,fresh_funds='unknown',conditions=note,rate_pct=number(value),rate_basis=s['rate_basis'],
                    valid_from=s.get('valid_from'),valid_to=None,availability='available',evidence=[dict(page_id=s['page_id'],quote=quote,locator=s['id']+'/'+lane)]+s['basis_evidence'])
                result.append(normalize(r))
    return result

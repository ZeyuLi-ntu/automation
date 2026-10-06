"""Bind literal table cells using each extraction lane's own evidence only."""
import re
from copy import deepcopy
from decimal import Decimal

def align_tables(offers,terms,pages,lane):
    changes=[]
    icbc=[r for r in offers if r['bank']=='ICBC']
    if icbc:
        rebuilt=[]
        for t in terms:
            text=re.sub(r'\s+',' ',t['text']).strip()
            match=re.search(r'(Counter|E-Banking) Promotion Rates',text,re.I)
            if not match:continue
            channel='branch' if match[1].lower()=='counter' else 'online'
            heads=re.findall(r'SGD([\d,.]+K?)\s*\(inclusive\)\s*(?:to SGD([\d,.]+K?)|& Above)',text,re.I)
            expected=2 if channel=='branch' else 3
            if len(heads)!=expected:raise ValueError('ICBC amount columns ambiguous')
            def money(s):
                return str(int(Decimal(s.rstrip('Kk').replace(',',''))*(1000 if s.lower().endswith('k') else 1))) if s else None
            templates=[r for r in icbc if any(e['page_id']==t['page_id'] for e in r['evidence'])]
            if not templates:raise ValueError('ICBC own table lacks source template')
            pattern=r'(\d+)\s+(months?|years?)\s+'+r'\s+'.join([r'([\d.]+)%']*expected)
            rows=list(re.finditer(pattern,text,re.I))
            if not rows:raise ValueError('ICBC empty rate grid')
            for m in rows:
                tenor=int(m[1])*(12 if m[2].lower().startswith('year') else 1)
                for (lo,hi),rate in zip(heads,m.groups()[2:]):
                    template=next((r for r in templates if r['channel']==channel and r['amount_min']==money(lo)),templates[0])
                    row=deepcopy(template)
                    row.update(tenor_value=tenor,tenor_unit='M',channel=channel,amount_min=money(lo),amount_max=money(hi),min_inclusive=True,max_inclusive=False,rate_pct=str(Decimal(rate).normalize()))
                    row['evidence'].append(dict(page_id=t['page_id'],quote=m[0],locator=t['locator']+' / own table column '+lo))
                    rebuilt.append(row)
        if rebuilt:
            changes.append(dict(bank='ICBC',field='table_grid',before=len(icbc),after=len(rebuilt),lane=lane,source='own text or screenshot transcript'))
            offers[:]=[r for r in offers if r['bank']!='ICBC']+rebuilt
    for row in offers:
        if row['product_id']=='cimb-sgd-online' and lane=='llm':
            units=[(p,u) for p in pages for u in p.get('units',[]) if u['kind']=='rates' and u['product_ids']==['cimb-sgd-online']]
            if len(units)!=1:raise ValueError('CIMB needs one unambiguous own-text rate table')
            page,unit=units[0];text=unit['text'];grid={}
            if not re.search(r'PERSONAL BANKING.*PREFERRED BANKING',text,re.S):raise ValueError('CIMB column order changed')
            for m in re.finditer(r'(\d+)\s+Months\s+([\d.]+)\s+([\d.]+)(?=\s|$)',text,re.I):
                for audience,rate in zip(['personal','preferred'],m.groups()[1:]):
                    key=(int(m[1]),audience)
                    if key in grid:raise ValueError('Duplicate CIMB tenor row')
                    grid[key]=(str(Decimal(rate).normalize()),m[0])
            key=(row['tenor_value'],row['audience'])
            if row['tenor_unit']!='M' or key not in grid:raise ValueError('CIMB rate row association missing')
            rate,quote=grid[key]
            if row['rate_pct']!=rate:
                changes.append(dict(product=row['product_id'],tenor=row['tenor_value'],audience=row['audience'],field='rate_pct',before=row['rate_pct'],after=rate,lane=lane,source='own captured text grid'))
                row['rate_pct']=rate
                row['evidence'].append(dict(page_id=page['id'],quote=quote,locator='source table row / '+row['audience']))
        if row['bank']=='HLF':
            own=[t for t in terms if t['product_id']==row['product_id'] and t['page_id']==row['evidence'][0]['page_id']]
            matches=[]
            for t in own:
                table=re.search(r'Deposit Amount(.*?)Published rates',t['text'],re.S|re.I)
                if not table:continue
                for m in re.finditer(r'S\$([\d,]+)\s+to\s*(<|≤)\s*S\$([\d,]+)\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%',table[1]):
                    if Decimal(m[1].replace(',',''))!=Decimal(row['amount_min'] or '-1'):continue
                    rate_map=dict(zip([6,9,12],map(Decimal,m.groups()[3:])))
                    if row['tenor_value'] not in rate_map or rate_map[row['tenor_value']]!=Decimal(row['rate_pct']):raise ValueError('HLF own transcript rate does not match tier')
                    matches.append((m[3].replace(',',''),m[2]=='≤',t,m[0]))
            if len(matches)>1:raise ValueError('Ambiguous HLF own transcript range')
            if matches:
                maximum,inclusive,t,quote=matches[0]
                if (row['amount_max'],row['max_inclusive'])!=(maximum,inclusive):
                    changes.append(dict(product=row['product_id'],tenor=row['tenor_value'],field='amount_max',before=row['amount_max'],after=maximum,lane=lane,source='own text' if lane=='llm' else 'own screenshot transcript'))
                    row['amount_max']=maximum;row['max_inclusive']=inclusive
                    row['evidence'].append(dict(page_id=t['page_id'],quote=quote,locator=t['locator']+' / deposit tier'))
    return changes

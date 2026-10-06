"""Literal board tables to conditions; no inferred percentage units or minima."""
import re,shutil,hashlib
from decimal import Decimal
from pathlib import Path
from .common import load,save,digest
from .schema import normalize,key
from .board_batch import compact
from .workbook_policy import currency_in_scope

FX={'US Dollar':'USD','Sterling Pound':'GBP','Australian Dollar':'AUD','New Zealand Dollar':'NZD','Canadian Dollar':'CAD','Swiss Franc':'CHF','Euro':'EUR','Japanese Yen':'JPY'}
SCB_FX=['USD','GBP','AUD','NZD','EUR','CAD','HKD','CNH']
CIMB_FX=['USD','GBP','AUD','NZD','EUR','CAD','CNH']

def number(s):return str(Decimal(re.sub(r'[%\s,]|p\.a\.?','',s,flags=re.I)))

def tenor_values(label,plain_month=False):
    x=compact(label).replace('*','').replace('(newplacementsnotavailable)','')
    x=re.sub(r'^(\d+)-(month|mth)',r'\1\2',x)
    if plain_month or re.search(r'month|mth',x):
        x=re.sub(r'months?|mths?','',x)
        if re.fullmatch(r'\d+-\d+',x):
            a,b=map(int,x.split('-'));return [(i,'M') for i in range(a,b+1)]
        if re.fullmatch(r'\d+(,\d+)*',label.replace(' ','').replace('*','')) and ',' in label:return [(int(v),'M') for v in label.split(',')]
        if x.isdigit():return [(int(x),'M')]
    if re.fullmatch(r'\d+(?:wks?|weeks?)',x):return [(int(re.match(r'\d+',x)[0])*7,'D')]
    return [] # No guessed mapping for interval weeks or unsupported tenor text.

def amount_band(label):
    x=compact(label).replace('s$','').replace('sgd','').replace('$','').replace('(','').replace(')','')
    x=re.sub(r'(\d+(?:\.\d+)?)k',lambda m:str(Decimal(m[1])*1000),x)
    # Exact printed SCB separator typo; keep the original label in conditions.
    x={'25000t049999':'25000to49999'}.get(x,x)
    vals=re.findall(r'\d+(?:\.\d+)?',x)
    if not vals:return None,None,True,False
    if len(vals)==1:
        if 'below' in x or 'less' in x or x.startswith(('<','<=')):
            return None,vals[0],True, x.startswith('<=')
        return vals[0],None,not x.startswith('>'),False
    if len(vals)!=2:raise ValueError('Ambiguous amount condition '+label)
    return vals[0],vals[1],not x.startswith('>'),not ('<' in x or 'exclusive' in x)

def normalize_section(section,lane):
    if section.get('layout') in ['dbs-fx','uob-fx','rhb-fx','sbi-fx','cimb-sgd','hlb-hkd']:
        from .remaining_board import normalize_remaining
        return normalize_remaining(section,lane)
    if section.get('layout') in ['ocbc-sgd','ocbc-fx']:
        from .ocbc_board import normalize_ocbc_section
        return normalize_ocbc_section(section,lane)
    s=section;bank=s['bank'];grid=s['rows'];pid=s['product_id'];offers=[]
    basis=s.get('rate_basis') or ('annual_nominal' if bank in ['DBS','HSBC','Maybank','SingFinance','Singapura Finance','UOB','RHB'] else 'unknown')
    def add(cur,label,band,value,*,plain=False,product=None,channel='unknown',audience='personal',conditions='',minimum=None,upper=None,amount_cur=None,equivalent=False,exact_amount=False):
        if not currency_in_scope(cur) or compact(value) in ['-','–','—','n/a','n.a','']:return
        lo,hi,li,ui=amount_band(band)
        if minimum is not None:lo=str(max(Decimal(lo or '0'),Decimal(str(minimum))))
        if upper is not None:hi=str(upper);ui=False
        if exact_amount:hi=lo;li=True;ui=True
        for n,u in tenor_values(label,plain):
            note=conditions or '挂牌；'+band
            if bank=='Maybank' and cur=='SGD':
                if n==1:lo=str(max(Decimal(lo or '0'),Decimal(10000)))
                if n==36:note+='；仅同期限旧存款自动续期'
            if bank=='HLF':lo=str(max(Decimal(lo or '0'),Decimal(10000 if n<3 else 500)));hi=hi or '1000000'
            if bank=='Singapura Finance':lo=str(max(Decimal(lo or '0'),Decimal(5000 if n<3 else 500)))
            if bank=='RHB' and n in [1,2]:note+='；仅Commercial/Corporate客户';audience='unknown'
            if bank=='OCBC' and n>=24:note+='；仅同期限旧存款续期'
            if 'rollover' in pid:note+='；仅同期限旧存款自动续期'
            display='定期存款挂牌'
            if 'premier' in pid:display='卓越理财挂牌'
            if 'isavvy' in pid:display='iSAVvy 外币定存挂牌'
            elif re.search(r'tier(\d+)',pid):display='外币定存挂牌 · 档位 '+re.search(r'tier(\d+)',pid)[1]
            if 'rollover' in pid:display='旧存款自动续期挂牌'
            if bank=='BEA' and s.get('layout')=='bea-fx':display='外币阶梯挂牌' if s['table']==1 else '外币挂牌'
            offer=dict(bank=bank,product_id=product or pid,product_name=display,currency=cur,rate_type='board',tenor_value=n,tenor_unit=u,
                audience=audience,channel=channel,amount_min=lo,amount_max=hi,min_inclusive=li,max_inclusive=ui,amount_currency=amount_cur or cur,amount_is_equivalent=equivalent,fresh_funds='unknown',conditions=note,
                rate_pct=number(value),rate_basis=basis,valid_from=s.get('valid_from'),valid_to=None,availability='available',evidence=[dict(page_id=s['page_id'],quote=' | '.join([band,label,value]),locator=s['id']+'/'+lane)])
            offer['evidence']+=s.get('extra_evidence',[])
            if s.get('layout')=='hsbc-fx-pdf':
                source_date=s.get('source_date') or s.get('valid_from')
                offer['valid_from']=None
                if source_date:offer['evidence'].append(dict(page_id=s['page_id'],quote='Rates as at: '+source_date,locator=s['id']+'/source-date'))
            offers.append(normalize(offer))
    if s.get('layout')=='icbc-board':
        cur=s['currency'];headers=grid[0][1:]
        for row in grid[1:]:
            if len(row)!=len(headers)+1:raise ValueError('ICBC board columns changed')
            for label,value in zip(headers,row[1:]):
                # USD's 500/20,000 note explicitly belongs to the promotional
                # table above it. Do not borrow that minimum for board rates.
                minimum=s.get('minimum') if cur!='USD' else None
                note='挂牌；'+row[0]
                if cur=='CNY':note+='；页面网上起存500，柜台起存20,000'
                if cur=='USD':note+='；按官网挂牌金额档位；挂牌起存门槛未另列，不套用促销门槛'
                add(cur,label,row[0],value,minimum=minimum,conditions=note)
    elif s.get('layout')=='bea-fx':
        terms=grid[1][1:]
        for row in grid[2:]:
            cur=row[1]
            if not currency_in_scope(cur):continue
            if len(row)!=len(terms)+3:raise ValueError('BEA foreign currency column mismatch')
            note='挂牌；达到SGD500,000等值须另询银行，不能直接套用本表'
            if s['table']==0:
                if row[2]!='USD10K/20K':raise ValueError('Unknown BEA Personal/Corporate minimum')
                for label,value in zip(terms,row[3:]):
                    add(cur,label,'10,000',value,amount_cur='USD',equivalent=True,audience='personal',conditions=note+'；Personal USD10,000等值；Corporate USD20,000等值另列')
                    add(cur,label,'20,000',value,amount_cur='USD',equivalent=True,audience='corporate',conditions=note+'；Corporate USD20,000等值')
            else:
                for label,value in zip(terms,row[3:]):add(cur,label,row[2],value,audience='all',conditions=note+'；Tier Rates；Minimum '+cur+' '+row[2])
    elif s.get('layout')=='bea-sgd':
        headers=grid[1]
        for row in grid[2:]:
            if len(row)!=len(headers)+1:raise ValueError('BEA SGD column mismatch')
            for band,value in zip(headers,row[1:]):add('SGD',row[0],band,value,conditions='SGD挂牌；金额列按官网原顺序对应')
    elif s.get('layout')=='hsbc-fx-pdf':
        headers=grid[1][1:]
        for row in grid[2:]:
            if len(row)!=len(headers)+1:raise ValueError('HSBC PDF continuation columns differ')
            for label,value in zip(headers,row[1:]):
                band=re.sub(r'\b'+s['currency'], '',row[0]).replace('\n',' ')
                add(s['currency'],label,band,value,audience=s['audience'],conditions='外币定存挂牌；'+s['audience'])
    elif bank=='Maybank' and s['currency']=='FX':
        start=next(i for i,r in enumerate(grid) if r[:2]==['Currency','Minimum']);terms=grid[start][2:]
        for row in grid[start+1:]:
            if row[0] not in FX:raise ValueError('Unknown Maybank currency')
            cur=FX[row[0]]
            for label,value in zip(terms,row[2:]):add(cur,label,row[1],value,plain=True,channel='online' if 'isavvy' in pid else 'unknown',conditions='挂牌；'+grid[0][0]+'；Minimum '+row[1])
    elif bank=='SCB' and s['currency']=='FX':
        cur=SCB_FX[s['table']]
        for row in grid[1:]:
            for label,value in zip(grid[0][1:],row[1:]):add(cur,label,row[0],value,product='scb-'+cur.lower()+'-board')
    elif bank=='CIMB':
        cur=CIMB_FX[s['table']]
        for row in grid[1:]:
                for label,value in zip(grid[0][1:],row[1:]):add(cur,row[0],label,value,plain=True,product='cimb-'+cur.lower()+'-board',exact_amount=s.get('amount_mode')=='quoted_point',conditions='挂牌；官网金额列 '+label+('；按原金额报价点展示，不外推区间' if s.get('amount_mode')=='quoted_point' else '，列边界含义待核'))
    elif bank in ['HSBC','SCB','RHB','ICBC','CITI']:
        start=next(i for i,r in enumerate(grid) if len(r)>2)
        for row in grid[start+1:]:
            for label,value in zip(grid[start][1:],row[1:]):add('SGD',label,row[0],value,audience='premier' if 'premier' in pid else 'personal',conditions=('按账户总定存余额分档；' if bank=='DBS' else '')+'挂牌；'+row[0])
    else:
        start=1 if bank=='SingFinance' else next(i for i,r in enumerate(grid) if len(r)>2)
        headers=['Tenure']+grid[start] if bank=='SingFinance' else grid[start]
        for row in grid[start+1:]:
            if len(row)<2:continue # Maybank footnotes are separately verified.
            for label,value in zip(headers[1:],row[1:]):
                if bank=='HLF':label=re.sub(r'^(Board|Special)\s*Rates','',label).strip()
                add('SGD',row[0],label,value,plain=bank in ['Maybank','OCBC','HLF','Singapura Finance'],conditions=('按账户总定存余额分档；' if bank=='DBS' else '')+'挂牌；'+label)
    return offers

def validate_wave(root):
    root=Path(root);run=load(root/'run.json');proof=load(root/'wave-checks.json')
    if run['errors']:raise ValueError('Capture incomplete: '+str(run['errors']))
    if proof['task_hash']!=digest(run['tasks']) or not proof['passed']:raise ValueError('Unresolved literal verification')
    actual={(c['task'],c['lane'],c['task_hash']) for c in proof['checks'] if c['passed']}
    expected={(t['id'],l,digest(t)) for t in run['tasks'] for l in ['llm','vlm']}
    if actual!=expected:raise ValueError('Missing evidence checks')
    for task in run['tasks']:
        for name,sha in task['image_hashes'].items():
            if hashlib.sha256((root/'evidence'/name).read_bytes()).hexdigest()!=sha:raise ValueError('Image changed')
    for name,sha in run.get('source_file_hashes',{}).items():
        if hashlib.sha256((root/'evidence'/name).read_bytes()).hexdigest()!=sha:raise ValueError('Original PDF changed')
    return run

def combine(base,waves,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);(out/'evidence').mkdir();r=load(Path(base)/'run.json');sources=[(Path(base),r)]
    for root in waves:sources.append((Path(root),validate_wave(root)))
    r=dict(id=out.name,as_of=max(x['as_of'] for _,x in sources),pages=[],bank_dates={},parents=[str(p.resolve()) for p,_ in sources],demo=False,errors=[],manual_catalog=[],coverage=[c for _,x in sources for c in x.get('coverage',[])],wide_sources=[str(Path(p).resolve()) for p in waves])
    for lane in ['llm','vlm']:r[lane]=dict(offers=[],inventory=[],coverage_complete=True,unreadable=[])
    for root,x in sources:
        r['pages']+=x['pages'];r['bank_dates'].update(x['bank_dates'])
        for f in (root/'evidence').iterdir():
            if not f.is_file() or f.name=='index.html':continue
            dest=out/'evidence'/f.name
            if dest.exists() and dest.read_bytes()!=f.read_bytes():raise ValueError('Evidence name collision')
            shutil.copy2(f,dest)
        for lane in ['llm','vlm']:
            offers=[o for s in x['sections'] for o in normalize_section(s,lane)] if 'sections' in x else x[lane]['offers']
            r[lane]['offers'] += [o for o in offers if currency_in_scope(o['currency'])]
    for o in r['llm']['offers']:
        item={k:o[k] for k in ['bank','product_id','currency','rate_type','amount_currency']}
        if item not in r['manual_catalog']:r['manual_catalog'].append(item)
    r['evidence_hash']=digest(r['pages']);r['rate_scopes']=[dict(currency=c,rate_type='board') for c in sorted({o['currency'] for o in r['llm']['offers']})]
    save(out/'run.json',r)
    from .pipeline import evidence_index
    evidence_index(r['pages'],out/'evidence');return r

def replace_verified_sections(base,wave,out):
    """Refresh only the repaired products, preserving other banks and evidence."""
    from copy import deepcopy
    base=Path(base);wave=Path(wave);out=Path(out);fresh=validate_wave(wave);prior=load(base/'run.json')
    added={lane:[o for s in fresh['sections'] for o in normalize_section(s,lane)] for lane in ['llm','vlm']}
    # Failed refreshed sections must not leave yesterday's quotes active.
    enrolled=load(Path(fresh['qualification_source'])/'run.json') if fresh.get('qualification_source') else fresh
    all_enrolled=[o for s in enrolled['sections'] for o in normalize_section(s,'llm')]
    scopes={(o['bank'],o['currency'],o['product_id']) for o in all_enrolled}
    from .board_freshness import compare_publication_dates,scope
    retain,date_events=compare_publication_dates(prior['llm']['offers'],added['llm'],fresh['as_of'])
    scopes-=retain
    for lane in ['llm','vlm']:added[lane]=[o for o in added[lane] if scope(o) not in retain]
    r=deepcopy(prior);r.update(id=out.name,as_of=max(prior['as_of'],fresh['as_of']),parents=[str(base.resolve()),str(wave.resolve())])
    r['wide_sources']=list(dict.fromkeys(prior.get('wide_sources',[])+[str(wave.resolve())]))
    r['source_date_events']=prior.get('source_date_events',[])+date_events
    r['pages']+=fresh['pages'];r['bank_dates'].update(fresh['bank_dates'])
    for lane in ['llm','vlm']:
        r[lane]['offers']=[o for o in prior[lane]['offers'] if (o['bank'],o['currency'],o['product_id']) not in scopes]+added[lane]
        ids=[key(o) for o in r[lane]['offers']]
        if len(ids)!=len(set(ids)):raise ValueError('Refresh produced duplicate conditions')
    repaired={(o['bank'],o['currency']) for o in all_enrolled}
    def coverage_pair(c):
        cur=c.get('currency')
        if cur=='FX' and c['bank'] in ['SCB','CIMB']:
            cur=(SCB_FX if c['bank']=='SCB' else CIMB_FX)[int(c['section'].rsplit('-',1)[1])]
        return c['bank'],cur
    r['coverage']=[c for c in prior.get('coverage',[]) if coverage_pair(c) not in repaired]+fresh.get('coverage',[])
    r['manual_catalog']=[]
    for o in r['llm']['offers']:
        item={k:o[k] for k in ['bank','product_id','currency','rate_type','amount_currency']}
        if item not in r['manual_catalog']:r['manual_catalog'].append(item)
    r['rate_scopes']=[dict(currency=c,rate_type='board') for c in sorted({o['currency'] for o in r['llm']['offers']})]
    r['evidence_hash']=digest(r['pages']);out.mkdir(parents=True,exist_ok=False);(out/'evidence').mkdir()
    for root in [base,wave]:
        for f in (root/'evidence').iterdir():
            if not f.is_file() or f.name=='index.html':continue
            dest=out/'evidence'/f.name
            if dest.exists() and dest.read_bytes()!=f.read_bytes():raise ValueError('Evidence filename collision')
            shutil.copy2(f,dest)
    save(out/'run.json',r)
    from .pipeline import evidence_index
    evidence_index(r['pages'],out/'evidence');return r

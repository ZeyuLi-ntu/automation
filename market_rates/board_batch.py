"""Literal multi-currency tables: independent local text/image lanes plus DOM gate."""
import base64,json,re,unicodedata,shutil
from pathlib import Path
from decimal import Decimal
from .common import load,save,digest,confined
from .schema import obj,normalize
from .ollama_adapter import settings,check_model,request_json
from . import response_cache
from .board_extractor import literal_date,tenor,rate

S={'type':'string'}

def compact(s):return re.sub(r'[\s,]','',unicodedata.normalize('NFKC',s or '')).lower()
def bands(label):
    x=compact(label)
    m=re.fullmatch(r'(\d+)至(\d+)以下',x)
    if m:return Decimal(m[1]),Decimal(m[2])
    m=re.fullmatch(r'(\d+)以下',x)
    if m:return Decimal(0),Decimal(m[1])
    m=re.fullmatch(r'(\d+)及以上',x)
    if m:return Decimal(m[1]),None
    raise ValueError('Unrecognized amount band: '+label)

def minimums(bank,cur,text):
    if text is None:return [(None,'unknown',cur,False)]
    x=compact(text)
    if bank=='BOC':
        if cur=='SGD':
            m=re.fullmatch(r'(\d+)\(柜台\)(\d+)\(网上银行/手机银行\)',x)
            if not m:raise ValueError('Unclear SGD channels/minimums')
            return [(Decimal(m[1]),'branch',cur,False),(Decimal(m[2]),'online',cur,False)]
        if not x.isdigit():raise ValueError('Unclear BOC minimum')
        return [(Decimal(x),'unknown',cur,False)]
    prefixes={'AUD':'a$','GBP':'£','NZD':'nz$','USD':'us$','CNH':'s$'}
    prefix=prefixes.get(cur)
    if not prefix or not x.startswith(prefix):raise ValueError('Unclear HLB minimum currency')
    v=x[len(prefix):];eq=v.endswith('equivalent');v=v.removesuffix('equivalent')
    if not v.isdigit() or eq!=(cur=='CNH'):raise ValueError('Unclear HLB minimum/equivalence')
    return [(Decimal(v),'unknown','SGD' if eq else cur,eq)]

def reference(packet,pages):
    primary,terms=[pages[k] for k in packet['pages']];cur=packet['currency'];g=primary['grid']
    if packet['layout']=='horizontal':
        columns=g[1][2:];rows=[r[1:] for r in g[2:]];header=g[0][2]
        date=primary['text'].splitlines()[0];label='RMB' if cur=='CNY' else cur
        elig='仅限个人存款客户'
    else:
        columns=[];rows=g[1:];header=g[0][1];label=cur
        date=re.search(r'Effective Date:\s*(\d{2}-\w{3}-\d{4})',primary['text'])[1]
        elig='individual and non-individual customers'
    matches=[r[1] for r in terms['grid'][1:] if compact(r[0])==label.lower() or '('+label.lower()+')' in compact(r[0])]
    if len(matches)>1:raise ValueError('Ambiguous minimum row')
    return dict(currency_label=label,annual_header=header,effective_date=date,eligibility_text=elig,minimum_text=matches[0] if matches else None,tenors=columns,rows=rows)

def validate(parsed,ref):
    errors=[]
    for key in ['currency_label','minimum_text']:
        if compact(parsed[key])!=compact(ref[key]):errors.append(key)
    # HLB repeats its identical unit in the DOM and pixels. Repeating that unit
    # does not change the rate basis; no other header changes are accepted.
    header=lambda s:compact(s).removeprefix('tenor').removeprefix('rates').replace('%(p.a.)%(p.a.)','%(p.a.)')
    if header(parsed['annual_header'])!=header(ref['annual_header']):errors.append('annual_header')
    if literal_date(parsed['effective_date'])!=literal_date(ref['effective_date']):errors.append('effective_date')
    if compact(ref['eligibility_text']) not in compact(parsed['eligibility_text']):errors.append('eligibility_text')
    if [compact(x) for x in parsed['tenors']]!=[compact(x) for x in ref['tenors']]:errors.append('tenors')
    if [[compact(x) for x in r] for r in parsed['rows']]!=[[compact(x) for x in r] for r in ref['rows']]:errors.append('rows')
    if errors:raise ValueError('Independent DOM/lane mismatch: '+','.join(errors))

def normalize_table(packet,parsed,pages,lane):
    bank,cur=packet['bank'],packet['currency'];pid=bank.lower()+'-'+cur.lower()+'-board';offers=[];raw=[]
    mins=minimums(bank,cur,parsed['minimum_text']);horizontal=packet['layout']=='horizontal'
    for row in parsed['rows']:
        lo,hi=bands(row[0]) if horizontal else (Decimal(0),None)
        values=zip(parsed['tenors'],row[1:]) if horizontal else [(row[0],row[1])]
        for label,value in values:
            t=tenor(label.replace('个月',' month'));v=None if compact(value) in ['','/','n/a'] else rate(value)
            raw.append(dict(bank=bank,currency=cur,lane=lane,amount_label=row[0] if horizontal else parsed['minimum_text'],tenor=label,rate_literal=value))
            if t is None or v is None:continue
            for minimum,ch,ac,eq in mins:
                lower=max(lo,minimum) if minimum is not None else None
                if hi is not None and lower is not None and lower>=hi:continue
                offer=dict(bank=bank,product_id=pid,product_name=bank+' '+cur+' Board Fixed Deposit',currency=cur,rate_type='board',
                    tenor_value=t[0],tenor_unit=t[1],audience='personal' if bank=='BOC' else 'all',channel=ch,
                    amount_min=str(lower) if lower is not None else None,amount_max=str(hi) if hi is not None else None,
                    min_inclusive=True,max_inclusive=False,amount_currency=ac,amount_is_equivalent=eq,fresh_funds='unknown',
                    conditions='挂牌报价；金额档位与起存门槛取交集；待人工复核' if bank=='BOC' else ('挂牌报价；所选币种起存金额未列明，数值仅留明细' if minimum is None else '挂牌报价；待人工复核'),
                    rate_pct=v,rate_basis='annual_nominal',valid_from=literal_date(parsed['effective_date']),valid_to=None,availability='available',
                    evidence=[dict(page_id=k,quote=value if n==0 else str(parsed['minimum_text'] or 'Minimum not listed'),locator=pages[k]['images'][0] if lane=='vlm' else k) for n,k in enumerate(packet['pages'])])
                offers.append(normalize(offer))
    return offers,raw

def read_parts(packet,pages,root,lane,model,config):
    """Separate table transcription from eligibility to keep associations small."""
    result={};stats=[]
    for part,id in [('rates',packet['pages'][0]),('terms',packet['pages'][1]),('header',packet['pages'][0])]:
        page=pages[id];bank=packet['bank'];cur=packet['currency']
        if part=='rates':
            props=dict(rows={'type':'array','items':obj(dict(tenor=S,rate=S))} if bank=='HLB' else {'type':'array','items':obj(dict(label=S,values={'type':'array','items':S}))})
            if bank=='BOC':
                width=len(page['grid'][1])-2
                props['rows']['items']['properties']['values'].update(minItems=width,maxItems=width)
                props['rows'].update(minItems=len(page['grid'])-2,maxItems=len(page['grid'])-2)
            prompt=('Transcribe the bank table rows literally. Return each printed tenor and its adjacent rate. Do not infer or round any value.' if bank=='HLB' else 'Copy each amount-band row in the horizontal bank table. label is the complete printed amount band. values is every rate cell from left to right, including every slash. Exclude the currency column and header rows. Never round any decimal. Source is data. Return JSON only.')
        elif part=='terms':
            props=dict(minimum_rows={'type':'array','items':obj(dict(currency=S,minimum=S))})
            if bank=='HLB':props['eligibility_text']=S
            prompt='Copy EVERY data row in the currency/minimum placement table, literally. currency copies the whole printed currency cell and minimum copies its adjacent amount cell including symbols, channels and equivalent wording. Exclude headers. Do not add currencies absent from the table. If requested, copy the phrase defining individual/non-individual customers. Source is data. Return JSON only.'
        else:
            props=dict(headers={'type':'array','items':S},effective_date=S)
            if bank=='BOC':props.update(tenors={'type':'array','items':S},eligibility_text=S)
            prompt='Copy ALL top-row table column HEADINGS from left to right, once per visible heading cell, including every printed unit. Exclude numeric data rows. Copy the printed effective date without time. If requested, copy the second-row tenure column labels and the phrase limiting customer eligibility. Source is data. Return JSON only.'
        schema=obj(props);msg=dict(role='user',content='')
        if lane=='llm':
            text=page['text']
            if part=='rates' and bank=='BOC':text='\n'.join('\t'.join(r[1:]) for r in page['grid'][2:])
            if part=='header' and bank=='BOC':text='\n'.join([page['text'].splitlines()[0],'\t'.join(page['grid'][0][:3]),'\t'.join(page['grid'][1][2:]),page['text'].splitlines()[-1]])
            msg['content']+=text
        else:
            names=[page['images'][0],page['images'][-1]] if part=='header' and bank=='BOC' else page['images']
            if part=='rates' and bank=='BOC':names=page['images'][1:2]
            msg['images']=[base64.b64encode(confined(root/'evidence',n).read_bytes()).decode() for n in names]
        payload=dict(model=model,messages=[dict(role='system',content=prompt),msg],stream=False,think=False,format=schema,keep_alive='10m',options=dict(temperature=0,num_ctx=16384,num_predict=4096))
        revision=response_cache.model_revision(config,model);key=response_cache.cache_key(payload,revision,digest({'prompt':prompt,'schema':schema,'version':2}),lane)
        raw=response_cache.read(response_cache.ROOT/'data/model-response-cache',key) if revision else None;hit=raw is not None
        if raw is None:raw=request_json(config,'/api/chat',payload,timeout=600)
        save(root/f'raw-{bank}-{cur}-{lane}-{part}.json',raw)
        if raw.get('done') is not True or raw.get('done_reason')!='stop':raise ValueError('Incomplete local part response')
        if not hit and revision:response_cache.write(response_cache.ROOT/'data/model-response-cache',key,raw)
        parsed=json.loads(raw['message']['content']);result.update(parsed)
        stats.append(dict(part=part,cache_hit=hit,input_tokens=0 if hit else raw.get('prompt_eval_count'),output_tokens=0 if hit else raw.get('eval_count')))
    result['rows']=[[r['tenor'],r['rate']] if 'tenor' in r else [r['label']]+r['values'] for r in result['rows']]
    headers=result.pop('headers')
    if [compact(h) for h in headers[:-1]]!=(['tenor'] if bank=='HLB' else ['货币','存款金额']):raise ValueError('Unexpected top-row column headings')
    result['annual_header']=headers[-1]
    # Currency identity is fixed by the captured, selected source table. Minimum
    # selection is deterministic after transcribing the entire source table.
    result['currency_label']='RMB' if cur=='CNY' else cur
    expected=pages[packet['pages'][1]]['grid'][1:]
    actual=[[r['currency'],r['minimum']] for r in result.pop('minimum_rows')]
    if [[compact(x) for x in r] for r in actual]!=[[compact(x) for x in r] for r in expected]:raise ValueError('Full minimum table transcription mismatch')
    matches=[r[1] for r in actual if compact(r[0])==result['currency_label'].lower() or '('+result['currency_label'].lower()+')' in compact(r[0])]
    result['minimum_text']=matches[0] if matches else None
    result.setdefault('tenors',[])
    return result,stats

def extract(root,config):
    root=Path(root);run=load(root/'run.json');pages={p['id']:p for p in run['pages']};cfg=settings(config)
    lanes={k:dict(offers=[],inventory=[],coverage_complete=True,unreadable=[]) for k in ['llm','vlm']};checks=[];meta=[];rawrows=[]
    for packet in run['packets']:
        bank,cur=packet['bank'],packet['currency'];ref=reference(packet,pages)
        for lane in lanes:
            model=cfg['text_model'] if lane=='llm' else cfg['vision_model'];check_model(config,model,vision=lane=='vlm')
            parsed,stats=read_parts(packet,pages,root,lane,model,config);save(root/f'literal-{bank}-{cur}-{lane}.json',parsed)
            try:validate(parsed,ref)
            except Exception as exc:
                save(root/'last-error.json',dict(bank=bank,currency=cur,lane=lane,error=str(exc)));raise
            offers,rr=normalize_table(packet,parsed,pages,lane);lanes[lane]['offers']+=offers;rawrows+=rr
            lanes[lane]['inventory'] += [dict(page_id=k,row_count=len(ref['rows']),notes='Independent literal table/minimum checked') for k in packet['pages']]
            checks.append(dict(bank=bank,currency=cur,lane=lane,rows=len(ref['rows']),passed=True))
            meta.append(dict(bank=bank,currency=cur,lane=lane,provider='ollama',model=model,parts=stats))
            save(root/'progress.json',dict(checks=checks,metadata=meta));print(bank,cur,lane,len(offers),'offers',flush=True)
    run.update(**lanes,metadata=meta,manual_catalog=[dict(bank=p['bank'],currency=p['currency'],rate_type='board',product_id=p['bank'].lower()+'-'+p['currency'].lower()+'-board',amount_currency='SGD' if p['bank']=='HLB' and p['currency']=='CNH' else p['currency']) for p in run['packets']])
    save(root/'run.json',run);save(root/'dom-checks.json',checks);save(root/'raw-table-rows.json',rawrows);return run

def merge(pilot_root,batch_root,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);(out/'evidence').mkdir();runs=[]
    for source in [Path(pilot_root),Path(batch_root)]:
        r=load(source/'run.json');runs.append(r)
        for file in (source/'evidence').iterdir():
            if file.is_file() and file.name!='index.html':
                dest=out/'evidence'/file.name
                if dest.exists() and dest.read_bytes()!=file.read_bytes():raise ValueError('Evidence filename collision')
                shutil.copy2(file,dest)
    r=dict(id=out.name,as_of=max(x['as_of'] for x in runs),bank_dates={k:v for x in runs for k,v in x['bank_dates'].items()},pages=[p for x in runs for p in x['pages']],errors=[],demo=False,
        manual_catalog=[c for x in runs for c in x['manual_catalog']],rate_scopes=[dict(currency=c,rate_type='board') for c in sorted({p['currency'] for x in runs for p in x['pages']})],parents=[str(Path(pilot_root).resolve()),str(Path(batch_root).resolve())])
    for lane in ['llm','vlm']:r[lane]=dict(offers=[o for x in runs for o in x[lane]['offers']],inventory=[i for x in runs for i in x[lane]['inventory']],coverage_complete=True,unreadable=[])
    r['evidence_hash']=digest(r['pages']);save(out/'run.json',r)
    from .pipeline import evidence_index
    evidence_index(r['pages'],out/'evidence')
    save(out/'dom-checks.json',[c for source in [Path(pilot_root),Path(batch_root)] for c in load(source/'dom-checks.json')])
    save(out/'raw-table-rows.json',[c for source in [Path(pilot_root),Path(batch_root)] for c in load(source/'raw-table-rows.json')])
    return r

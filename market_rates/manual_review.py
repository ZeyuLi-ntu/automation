"""Human revisions are separate from immutable text/vision model evidence."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from .common import load,save,digest
from .schema import FACTS, normalize, group_key,financial_terms
from .workbook_policy import bank_in_scope,currency_in_scope
from .weekly_history import identity

ROOT=Path(__file__).resolve().parents[1]
EDITABLE={'rate_pct','product_name','audience','channel','amount_min','amount_max','min_inclusive','max_inclusive',
          'fresh_funds','conditions','valid_from','valid_to','rate_basis','availability','tenor_value','tenor_unit','amount_currency','amount_is_equivalent'}

def catalog(run):
    from .multi_bank_validation import BASE
    if run.get('manual_catalog'):return [c for c in run['manual_catalog'] if currency_in_scope(c['currency'])]
    banks=(set(run.get('bank_dates',{})) or {p['bank'] for p in run.get('pages',[])}) | {c['bank'] for c in run.get('coverage',[])}
    return [dict(bank=b,product_id=BASE[b],currency='SGD',rate_type='promo',amount_currency='SGD') for b in sorted(banks) if b in BASE and bank_in_scope(b)]

def ledger(project=ROOT):
    p=Path(project)/'data/manual-review.json'
    return load(p) if p.exists() else dict(version=0,revisions=[])

def scope(run):return digest({'as_of':run['as_of'],'evidence_hash':run.get('evidence_hash')})

def add_offer(run,document,project=ROOT):
    from .multi_bank_validation import BASE
    state=ledger(project)
    if document.get('version')!=state['version']:raise ValueError('其他窗口已修改，请刷新。')
    author=str(document.get('author','')).strip();reason=str(document.get('reason','')).strip()
    url=str(document.get('source_url','')).strip();quote=str(document.get('source_quote','')).strip()
    from urllib.parse import urlsplit
    if not author or not reason or not quote or urlsplit(url).scheme not in ['https','http']:raise ValueError('补录须填写复核人、原因、来源网址及原文摘录。')
    fields=document.get('fields',{});bank=document.get('bank')
    allowed_banks=(set(run.get('bank_dates',{})) or {p['bank'] for p in run.get('pages',[])}) | {c['bank'] for c in run.get('coverage',[]) if c.get('numeric_insertion') is False}
    choices=[c for c in catalog(run) if c['bank']==bank and (not document.get('catalog_id') or digest(c)==document['catalog_id'])]
    if len(choices)!=1 or not bank_in_scope(bank) or bank not in allowed_banks or set(fields)-EDITABLE:raise ValueError('请选择本批已配置的银行、币种与产品；新范围须先建立插表映射。')
    selected=choices[0]
    key='manual-'+digest([scope(run),state['version'],fields])[:20]
    row=dict(bank=bank,product_id=selected['product_id'],currency=selected['currency'],rate_type=selected['rate_type'],amount_currency=selected['amount_currency'],amount_is_equivalent=False,
        evidence=[dict(page_id=key,quote=quote,locator='人工补录来源：'+url)])
    row.update(fields)
    row=normalize(row)
    if row['rate_pct'] is None or not Decimal('0')<=Decimal(row['rate_pct'])<=Decimal('25'):raise ValueError('请输入有效百分数利率。')
    if any(identity(row)==identity(i['effective'] or i['original']) for i in items(run,project)):raise ValueError('同条件报价已存在，请修改原条目。')
    revision=dict(id=key,fingerprint=scope(run),action='add',offer=row,fields={},persist=False,author=author,reason=reason,
        note=str(document.get('note','')).strip(),source_url=url,source_quote=quote,at=datetime.now(timezone.utc).isoformat(),run_id=run['id'],revision=state['version']+1)
    state['revisions'].append(revision);state['version']+=1;save(Path(project)/'data/manual-review.json',state);return revision

def items(run,project=ROOT):
    rows=defaultdict(lambda:dict(llm=[],vlm=[]))
    for lane in ['llm','vlm']:
        for row in run.get(lane,{}).get('offers',[]):
            if currency_in_scope(row['currency']):rows[identity(row)][lane].append(row)
    pages={p['id']:p for p in run.get('pages',[])};revisions=ledger(project)['revisions'];current={}
    for r in revisions:current[(r['id'],r['fingerprint'])]=r
    result=[]
    for key,pair in rows.items():
        refs=sorted({e['page_id'] for lane in pair.values() for row in lane for e in row['evidence']})
        fingerprint=digest(dict(pair=pair,evidence={k:pages.get(k,{}).get('image_hashes',{}) for k in refs}))
        left,right=pair['llm'],pair['vlm']
        equal=len(left)==len(right)==1 and all(left[0][f]==right[0][f] for f in FACTS if f!='conditions') and financial_terms(left[0])==financial_terms(right[0])
        original=(left or right)[0];decision=current.get((key,fingerprint))
        if decision and decision['action']=='reset':decision=None
        selected=decision.get('offer') if decision else original
        result.append(dict(id=key,fingerprint=fingerprint,bank=original['bank'],product_id=original['product_id'],
            original=original,effective=selected,agreed=equal,decision=decision,**pair,
            evidence=[dict(id=k,url=pages.get(k,{}).get('url',''),text=pages.get(k,{}).get('text',''),images=pages.get(k,{}).get('images',[]),origin=pages.get(k,{}).get('evidence_origin')) for k in refs]))
    for key,revision in current.items():
        addition=next((v for v in revisions if v['id']==key[0] and v['action']=='add'),None)
        if addition and addition['fingerprint']==scope(run) and revision['action']!='reset':
            original=addition['offer'];result.append(dict(id=key[0],fingerprint=key[1],bank=original['bank'],product_id=original['product_id'],
              original=original,effective=revision['offer'],agreed=False,decision=revision,llm=[],vlm=[],
              evidence=[dict(id=key[0],url=addition['source_url'],text=addition['source_quote'],images=[])]))
    return sorted(result,key=lambda x:(x['bank'],x['product_id'],x['original']['tenor_value'],x['id']))

def record(run,document,project=ROOT):
    state=ledger(project)
    if document.get('version')!=state['version']:raise ValueError('其他窗口已保存修改，请刷新后再保存。')
    author=str(document.get('author','')).strip();reason=str(document.get('reason','')).strip()
    if not author or not reason:raise ValueError('请填写复核人和修正／确认原因。')
    item=next((i for i in items(run,project) if i['id']==document.get('id')),None)
    if not item or item['fingerprint']!=document.get('fingerprint'):raise ValueError('原始证据已变化，请刷新后重新核实。')
    action=document.get('action');offer=None;fields={}
    if action not in ('confirm','llm','vlm','replace','exclude','reset'):raise ValueError('不支持的复核动作。')
    if action in ('llm','vlm'):
        if len(item[action])!=1:raise ValueError('该路线缺失或有重复记录，请改用人工修正。')
        offer=deepcopy(item[action][0])
    elif action=='confirm':
        if not item['agreed']:raise ValueError('两路有分歧，请明确选用一路或填写修正值。')
        offer=deepcopy(item['effective'] or item['original'])
    elif action=='replace':
        patch=document.get('fields',{})
        if set(patch)-EDITABLE:raise ValueError('不能修改银行、产品身份或原始证据。')
        offer=deepcopy(item['original']);offer.update(patch)
    if offer:
        offer=normalize(offer)
        if (offer['currency'],offer['rate_type'])!=(item['original']['currency'],item['original']['rate_type']):raise ValueError('不可把原报价改到其他币种或类别；请排除并按对应产品补录。')
        if offer['rate_pct'] is not None and not Decimal('0')<=Decimal(offer['rate_pct'])<=Decimal('25'):raise ValueError('请以百分数填写利率，例如 1.75。')
        if offer['availability']=='available' and offer['rate_pct'] is None:raise ValueError('有效报价必须填写利率。')
        fields={k:offer[k] for k in EDITABLE if offer[k]!=item['original'][k]}
    persist=bool(document.get('persist'))
    if persist and item['id'].startswith('manual-'):raise ValueError('补录报价仅适用于本次，请取消跨期沿用。')
    if persist and (not offer or set(fields)-{'rate_pct','product_name'}):raise ValueError('跨期沿用支持利率和产品显示名；资格、金额、期限及有效期调整仅适用于本次。')
    revision=dict(id=item['id'],fingerprint=item['fingerprint'],action=action,offer=offer,fields=fields,
        persist=persist,author=author,reason=reason,note=str(document.get('note','')).strip(),
        at=datetime.now(timezone.utc).isoformat(),run_id=run['id'],revision=state['version']+1)
    if item['id'].startswith('manual-'):
        revision['source_url']=item['evidence'][0]['url'];revision['source_quote']=item['evidence'][0]['text']
    state['revisions'].append(revision);state['version']+=1;save(Path(project)/'data/manual-review.json',state)
    return revision

def effective_offers(run,project=ROOT):
    accepted=[];blocked=set();receipts=[];persistent={}
    for r in ledger(project)['revisions']:
        # A reset or a later one-period decision explicitly stops old carry-forward.
        if r['persist'] and r['offer']:persistent[r['id']]=r
        else:persistent.pop(r['id'],None)
    for item in items(run,project):
        decision=item['decision']
        if decision:
            if decision['action']=='exclude':receipts.append(decision);continue
            row=deepcopy(decision['offer']);receipts.append(decision)
        elif item['agreed']:row=deepcopy(item['original'])
        else:blocked.add(group_key(item['original']));continue
        if not decision and item['id'] in persistent:
            prior=persistent[item['id']]
            if all(row[k]==prior['offer'][k] for k in ['valid_from','valid_to','rate_basis']):
                for field,value in prior['fields'].items():row[field]=value
                receipts.append(dict(prior,carried_forward=True,current_fingerprint=item['fingerprint']))
        accepted.append(row)
    # One conflicting tier blocks the entire product/tenor, including its Personal fallback.
    return [r for r in accepted if group_key(r) not in blocked],sorted(blocked),receipts

"""Independent regression fixture from reviewed frozen official tables.

Never imported by a model adapter. Numerical targets are evaluation-only.
"""
import argparse
from collections import Counter
from decimal import Decimal
import html
from pathlib import Path
import re
from market_rates.common import load,save
from market_rates.multi_bank_extractor import canonical_text
from market_rates.multi_bank_validation import matched_offers
from market_rates.pipeline import check_evidence
from market_rates.table_validation import sha

def reference():
    expected=[]
    def add(product,t,a,lo,hi,inc,rate,channel,start,end,fresh='unknown'):
        expected.append((product,t,a,str(lo),str(hi) if hi else None,inc,str(Decimal(str(rate)).normalize()),channel,start,end,fresh))
    for t,a,b in [(3,1.3,1.4),(6,1.7,1.8),(12,1.7,1.8)]:
        for aud,rate in [('personal',a),('premier',b)]:add('rhb-sgd-promo',t,aud,20000,None,False,rate,'branch_or_mobile','2026-09-11',None)
    for t,a,b in [(3,1.35,1.4),(6,1.75,1.8),(9,1.75,1.8),(12,1.8,1.85)]:
        for aud,rate in [('personal',a),('preferred',b)]:add('cimb-sgd-online',t,aud,10000,1000000,True,rate,'online','2026-09-21','2026-09-30')
        add('cimb-wwfd-online',t,'personal',10000,1000000,True,a,'online','2026-09-21','2026-09-30','no')
    add('cimb-preferred-welcome',6,'preferred',10000,250000,True,2.33,'unknown','2026-09-01','2026-09-30','yes')
    for t,lo,hi in [(6,1.45,1.5),(9,1.55,1.6),(12,1.65,1.7)]:
        add('hlf-branch-promo',t,'personal',20000,100000,False,lo,'branch_or_instruction','2026-09-25',None)
        add('hlf-branch-promo',t,'personal',100000,None,False,hi,'branch_or_instruction','2026-09-25',None)
        add('hlf-digital-promo',t,'personal',5000,20000,False,Decimal(str(lo))-Decimal('.05'),'hlf_digital','2026-09-25',None)
        add('hlf-digital-promo',t,'personal',20000,None,False,hi,'hlf_digital','2026-09-25',None)
    return expected

FIELDS=['product_id','tenor_value','audience','amount_min','amount_max','max_inclusive','rate_pct','channel','valid_from','valid_to','fresh_funds']
def tokens(s):
    s=re.sub(r'\[PDF page \d+\]','',s)
    return Counter(re.findall(r"[\w]+|[<>%]",canonical_text(s).casefold()))

def score(root):
    root=Path(root);run=load(root/'run.json');check_evidence(run,root/'evidence')
    # Pin the audited evidence once; a future date cannot inherit these answers.
    fixture=root/'reference.evidence-hash.json'
    if fixture.exists() and load(fixture)['evidence_hash']!=run['evidence_hash']:raise ValueError('Reference evidence changed')
    if run['as_of']!='2026-09-25':raise ValueError('This reference only applies to the frozen 2026-09-25 pilot')
    save(fixture,dict(evidence_hash=run['evidence_hash'],purpose='evaluation_only',expected=reference()))
    expected=Counter(reference());results={}
    for lane in ['llm','vlm']:
        got=Counter(tuple(r[k] for k in FIELDS) for r in run[lane]['offers'])
        results[lane]=dict(expected=sum(expected.values()),matched=sum((expected&got).values()),
                          missing=list((expected-got).elements()),unexpected=list((got-expected).elements()),coverage_complete=run[lane]['coverage_complete'])
    transcript={lane:{} for lane in ['llm','vlm']}
    for m in run['metadata']:
        for t in m.get('terms_transcripts',[]):transcript[m['lane']][t['unit']]=t
    terms=[]
    for unit in sorted(set(transcript['llm'])|set(transcript['vlm'])):
        a=transcript['llm'].get(unit,{});b=transcript['vlm'].get(unit,{})
        at,bt=tokens(a.get('text','')),tokens(b.get('text',''))
        terms.append(dict(unit=unit,product_id=a.get('product_id',b.get('product_id')),missing_words=list((at-bt).elements()),
                          additional_words=list((bt-at).elements()),llm=a,vlm=b,token_inventory_equal=bool(a and b and at==bt)))
    good,bad=matched_offers(run)
    result=dict(evidence_hash=run['evidence_hash'],run_sha256=sha(root/'run.json'),rows=len(good),blocked_groups=bad,lanes=results,terms=terms,
                limitation='Same local model with independent modalities. Agreement is not proof of accuracy. Full conditions remain human-reviewed.')
    save(root/'benchmark.json',result)
    parts=['<!doctype html><meta charset="utf-8"><style>body{font:16px Arial;max-width:1150px;margin:35px auto;line-height:1.6}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}pre{white-space:pre-wrap;font-size:14px}.note{background:#fff3cd;padding:15px}</style><h1>三家银行 · 提取与插表验证</h1>',
           '<p class="note">仅验证副本，尚未批准发布。采集日期：'+run['as_of']+'。同一本地模型分别读取文字与截图；两路一致后仍对照原文核验金额边界。</p>',
           '<p><a href="review.html">逐项报价复核</a> · <a href="evidence/index.html">原始证据</a></p><table><tr><th>路线</th><th>对照原文基准</th><th>覆盖</th></tr>']
    for lane,v in results.items():parts.append(f'<tr><td>{lane.upper()}</td><td>{v["matched"]}/{v["expected"]}</td><td>{v["coverage_complete"]}</td></tr>')
    parts.append('</table><h2>条款逐页对照</h2><p>词项一致只检查遗漏或增补，不代表条款含义、顺序和适用范围已批准。每页均保留双路全文。</p>')
    for t in terms:
        parts.append('<details><summary>'+html.escape(t['product_id']+' / '+t['unit'])+f'：缺少{len(t["missing_words"])}项、增加{len(t["additional_words"])}项</summary><p>文字来源：'+html.escape(t['llm'].get('locator',''))+'</p><pre>'+html.escape(t['llm'].get('text',''))+'</pre><p>视觉来源：'+html.escape(t['vlm'].get('locator',''))+'</p><pre>'+html.escape(t['vlm'].get('text',''))+'</pre></details>')
    (root/'benchmark.html').write_text(''.join(parts),encoding='utf8')
    print({k:(v['matched'],v['expected']) for k,v in results.items()},'blocked',bad,'term_units',len(terms))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);score(p.parse_args().run)

"""Frozen, visually checked official tables. Reference values never enter model prompts."""
import argparse
from collections import Counter
import html
from pathlib import Path
from market_rates.common import load,save
from market_rates.pipeline import check_evidence
from market_rates.multi_bank_validation import matched_offers
from market_rates.table_validation import sha
from scripts.score_three_bank_pilot import FIELDS,tokens
EVIDENCE='bee73cfee1c8bfeac022d287d85b13e610e3b3e1cd05315aa6ec7aaa959613ef'

def reference():
    rows=[]
    def add(pid,t,a,lo,hi,inc,rate,channel,start,end,fresh,basis='annual_nominal'):
        rows.append((pid,t,a,lo,hi,inc,rate,channel,start,end,fresh,True,basis))
    for t,rate in [(6,'1.6'),(10,'1.65'),(12,'1.7')]:add('uob-sgd-promo',t,'personal','10000','999999',True,rate,'online','2026-09-23','2026-10-31','yes')
    for t,branch,low,high in [(1,'1.05','1.05','1.1'),(3,'1.25','1.25','1.3'),(6,'1.55','1.3','1.6'),(9,'1.4','1.1','1.45'),(12,'1.4','1.15','1.45')]:
        for channel,lo,hi,rate in [('branch','20000',None,branch),('online','500','20000',low),('online','20000',None,high)]:
            add('icbc-sgd-promo',t,'all',lo,hi,False,rate,channel,None,None,'yes','unknown')
    for t in [4,8]:
        for lo,hi,rate in [('100000','199999.99','2.08'),('200000','250000','2.18')]:add('boc-sgd-welcome',t,'personal',lo,hi,True,rate,'online','2026-09-21','2026-09-27','unknown')
    for t,tiers in [(1,[('500','1.1')]),(2,[('500','1.2')]),(3,[('500','1.6')]),(5,[('500','1.5')]),(6,[('500','1.7'),('100000','1.75'),('200000','1.8')]),(9,[('500','1.55'),('200000','1.75')]),(12,[('500','1.7'),('100000','1.75'),('200000','1.8')]),(18,[('500','1.6'),('200000','1.65')]),(24,[('500','1.55')])]:
        for lo,rate in tiers:add('boc-sgd-mobile',t,'personal',lo,None,False,rate,'online','2026-09-21','2026-09-27','unknown')
    return rows

def score(root,expected_evidence):
    root=Path(root);run=load(root/'run.json');check_evidence(run,root/'evidence')
    if run['as_of']!='2026-09-26' or run['evidence_hash']!=expected_evidence or expected_evidence!=EVIDENCE:raise ValueError('Reference only covers the independently inspected frozen evidence')
    expected=Counter(reference());results={};fields=FIELDS+['min_inclusive','rate_basis']
    for lane in ['llm','vlm']:
        got=Counter(tuple(r[k] for k in fields) for r in run[lane]['offers'])
        results[lane]=dict(expected=sum(expected.values()),matched=sum((expected&got).values()),missing=list((expected-got).elements()),unexpected=list((got-expected).elements()),coverage_complete=run[lane]['coverage_complete'])
    good,bad=matched_offers(run);transcript={l:{} for l in ['llm','vlm']}
    for meta in run['metadata']:
        for t in meta.get('terms_transcripts',[]):transcript[meta['lane']][t['unit']]=t
    terms=[]
    for unit in sorted(set(transcript['llm'])|set(transcript['vlm'])):
        left=transcript['llm'].get(unit,{});right=transcript['vlm'].get(unit,{})
        a,b=tokens(left.get('text','')),tokens(right.get('text',''))
        terms.append(dict(unit=unit,llm=left,vlm=right,missing_words=list((a-b).elements()),additional_words=list((b-a).elements())))
    result=dict(kind='frozen_source_reference',evidence_hash=expected_evidence,run_sha256=sha(root/'run.json'),lanes=results,rows=len(good),blocked_groups=bad,terms=terms,
        limitations=['ICBC 原页及关联促销条款未写明年化单位；保留 rate_basis=unknown，待人工核实。','BOC 新客户活动期和本张利率有效期分开；本张报价只核实至 9 月 27 日。','BOC 2M、5M 保留原始明细，不插表。'])
    save(root/'benchmark.json',result)
    body=['<!doctype html><meta charset="utf-8"><style>body{font:16px Arial;max-width:1100px;margin:36px auto;line-height:1.6}pre{white-space:pre-wrap}td,th{border:1px solid #ddd;padding:8px}</style><h1>UOB / ICBC / BOC · 原文核验</h1><p>9月26日采集，37 条原始报价。基准独立对照官方截图和条款，未送入模型提示词。</p>']
    body+=['<p>'+html.escape(x)+'</p>' for x in result['limitations']]
    body.append('<p><a href="review.html">逐项复核</a> · <a href="evidence/index.html">完整原始证据</a></p><table><tr><th>路线</th><th>匹配</th><th>差异</th></tr>')
    for lane,v in results.items():body.append(f'<tr><td>{lane}</td><td>{v["matched"]}/{v["expected"]}</td><td>{html.escape(str(v["missing"]+v["unexpected"]))}</td></tr>')
    body.append('</table><h2>完整条款对照</h2>')
    for t in terms:body.append('<details><summary>'+html.escape(t['unit'])+f' · 缺少{len(t["missing_words"])} / 增加{len(t["additional_words"])}词项</summary><pre>'+html.escape(t['llm'].get('text',''))+'</pre><pre>'+html.escape(t['vlm'].get('text',''))+'</pre></details>')
    (root/'benchmark.html').write_text(''.join(body),encoding='utf8')
    print({l:(v['matched'],v['expected']) for l,v in results.items()},'blocked',bad)
    if bad or any(v['matched']!=v['expected'] or v['unexpected'] for v in results.values()):raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--evidence-hash',required=True);a=p.parse_args();score(a.run,a.evidence_hash)

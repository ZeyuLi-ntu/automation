"""Evaluation only: manually read official 26 September tables, never model input."""
import argparse
from collections import Counter
import html
from pathlib import Path
from market_rates.common import load,save
from market_rates.pipeline import check_evidence
from market_rates.multi_bank_validation import matched_offers
from market_rates.table_validation import sha
from scripts.score_three_bank_pilot import FIELDS,tokens

EVIDENCE='e7df418f13d8bc256c9beb15aca2b209064e6ab8855ab0541196491b0c0af813'

def reference():
    rows=[]
    for tenor,branch,online in [(6,'1.3','1.35'),(12,'1.45','1.5')]:
        for channel,rate,maximum in [('branch',branch,'5000000'),('online',online,'999999')]:
            rows.append(('ocbc-sgd-promo',tenor,'personal','20000',maximum,True,rate,channel,None,None,'yes'))
    for tenor,rate in [(6,'2.05'),(12,'2.05'),(18,'1.88'),(24,'2.1')]:
        for channel,minimum,start in [('online','10000','2026-09-24'),('branch','100000',None)]:
            rows.append(('hlb-sgd-promo',tenor,'all',minimum,None,False,rate,channel,start,None,'no'))
    for tenor,rate in [(6,'1.5'),(12,'1.4')]:rows.append(('sbi-sgd-promo',tenor,'personal','50000',None,False,rate,'branch',None,None,'no'))
    return rows

def score(root):
    root=Path(root);run=load(root/'run.json');check_evidence(run,root/'evidence')
    if run['evidence_hash']!=EVIDENCE or run['as_of']!='2026-09-26':raise ValueError('本基准仅适用已检查的冻结证据；新采集须重新核验')
    expected=Counter(reference());results={}
    for lane in ['llm','vlm']:
        got=Counter(tuple(r[k] for k in FIELDS) for r in run[lane]['offers'])
        results[lane]=dict(expected=sum(expected.values()),matched=sum((expected&got).values()),missing=list((expected-got).elements()),unexpected=list((got-expected).elements()),coverage_complete=run[lane]['coverage_complete'])
    good,bad=matched_offers(run);transcript={l:{} for l in ['llm','vlm']}
    for meta in run['metadata']:
        for t in meta.get('terms_transcripts',[]):transcript[meta['lane']][t['unit']]=t
    terms=[]
    for unit in sorted(set(transcript['llm'])|set(transcript['vlm'])):
        left=transcript['llm'].get(unit,{});right=transcript['vlm'].get(unit,{})
        a,b=tokens(left.get('text','')),tokens(right.get('text',''))
        terms.append(dict(unit=unit,llm=left,vlm=right,missing_words=list((a-b).elements()),additional_words=list((b-a).elements()),token_inventory_equal=bool(left and right and a==b)))
    result=dict(kind='frozen_source_reference',evidence_hash=EVIDENCE,run_sha256=sha(root/'run.json'),lanes=results,rows=len(good),blocked_groups=bad,terms=terms)
    save(root/'benchmark.json',result)
    body=['<!doctype html><meta charset="utf-8"><style>body{font:16px Arial;max-width:1100px;margin:36px auto;line-height:1.6}pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:10px}</style><h1>OCBC / HL Bank / SBI · 原文基准核验</h1><p>证据日：2026-09-26。两路使用同一本地模型；14 条报价对照冻结官方原文；完整条款仍待人工复核。</p><p>HL Bank：线上 9/24 生效；网页 9/24 与分行条款 9/23 冲突，分行开始日留空待核；赠礼条件未混入基本利率。SBI：个人多笔合计必须小于 S$1,000,000，未写成单笔上限。</p><p><a href="review.html">报价复核</a> · <a href="evidence/index.html">全部原始证据</a></p><table><tr><th>路线</th><th>原文基准</th><th>缺失/额外</th></tr>']
    for lane,v in results.items():body.append(f'<tr><td>{lane}</td><td>{v["matched"]}/{v["expected"]}</td><td>{html.escape(str(v["missing"]+v["unexpected"]))}</td></tr>')
    body.append('</table><h2>逐页完整条款对照</h2>')
    for t in terms:
        body.append('<details><summary>'+html.escape(t['unit'])+f'：缺少 {len(t["missing_words"])} 词项，增加 {len(t["additional_words"])} 词项</summary><p>文字</p><pre>'+html.escape(t['llm'].get('text',''))+'</pre><p>视觉</p><pre>'+html.escape(t['vlm'].get('text',''))+'</pre></details>')
    (root/'benchmark.html').write_text(''.join(body),encoding='utf8')
    print({l:(v['matched'],v['expected']) for l,v in results.items()},'blocked',bad)
    if bad or any(v['matched']!=v['expected'] or v['unexpected'] for v in results.values()):raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);score(p.parse_args().run)

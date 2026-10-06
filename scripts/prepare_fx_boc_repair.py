"""Add the checked latest BOC notice, preserving its published validity dates."""
import argparse,shutil
from pathlib import Path
from market_rates.common import load,save,digest
from market_rates.fx_promo import normalize_fx
from market_rates.board_wave import validate_wave
from market_rates.pipeline import check_evidence,evidence_index

def prepare(source,boc,out):
    source,boc,out=map(Path,[source,boc,out]);r=load(source/'run.json');proof=validate_wave(boc)
    quotes=[q for s in proof['sections'] for q in normalize_fx(s)]
    if len(quotes)!=28 or {q['currency'] for q in quotes}!={'USD','CNY','AUD','NZD','EUR','GBP'}:raise ValueError('Unexpected BOC coverage')
    shutil.copytree(source,out)
    for f in (boc/'evidence').iterdir():
        if f.is_file() and f.name!='index.html':shutil.copy2(f,out/'evidence'/f.name)
    known={p['id'] for p in r['pages']};r['pages'] += [p for p in proof['pages'] if p['id'] not in known]
    for lane in ['llm','vlm']:r[lane]['offers']=[q for q in r[lane]['offers'] if q['bank']!='BOC']+quotes
    r['deferred']=[q for q in r['deferred'] if q['offer']['bank']!='BOC'];r['id']=out.name;r['fx_sources'].append(str(boc.resolve()));r['evidence_hash']=digest(r['pages'])
    for q in quotes:
        cat={k:q[k] for k in ['bank','product_id','currency','rate_type','amount_currency']}
        if cat not in r['manual_catalog']:r['manual_catalog'].append(cat)
    r['boc_reference_policy']='用户2026-09-28确认按最新公开公告插表并注明公告期限；不修改valid_to。'
    save(out/'run.json',r);check_evidence(r,out/'evidence');evidence_index(r['pages'],out/'evidence');print('BOC checked quotes:',len(quotes))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--boc',required=True);a.add_argument('--out',required=True);x=a.parse_args();prepare(x.source,x.boc,x.out)

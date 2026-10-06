"""Replace one freshly qualified bank in an immutable combined SGD run."""
import argparse
from pathlib import Path
from copy import deepcopy
import shutil
from market_rates.common import load,save,digest
from market_rates.consolidate import qualify,consolidate
from market_rates.pipeline import check_evidence,evaluate,evidence_index
from market_rates.store import Store


def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--replacement',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();base=Path(a.base);fresh=Path(a.replacement);out=Path(a.out)
    qualify(fresh,allow_agreement=True)
    cfg=load(base/'config.snapshot.json');run=load(base/'run.json');check_evidence(run,base/'evidence')
    banks=set(load(fresh/'config.snapshot.json')['expected_banks'])
    if not banks or not banks.issubset(cfg['expected_banks']):raise ValueError('Replacement must belong to the base run')
    retained=out.with_name(out.name+'-retained');retained.mkdir()
    shutil.copytree(base/'evidence',retained/'evidence')
    run=deepcopy(run);run['id']=retained.name
    for key in ['pages','metadata']:run[key]=[x for x in run[key] if x.get('bank') not in banks]
    for lane in ['llm','vlm']:
        run[lane]['offers']=[r for r in run[lane]['offers'] if r['bank'] not in banks]
        ids={r['id'] for r in run['pages']}
        run[lane]['inventory']=[r for r in run[lane]['inventory'] if r.get('page_id') in ids]
    run['bank_dates']={k:v for k,v in run.get('bank_dates',{}).items() if k not in banks}
    run['evidence_hash']=digest(run['pages'])
    cfg['expected_banks']=[b for b in cfg['expected_banks'] if b not in banks]
    for key in ['sources','products']:cfg[key]=[r for r in cfg[key] if r['bank'] not in banks]
    save(retained/'config.snapshot.json',cfg);save(retained/'run.json',run);evidence_index(run['pages'],retained/'evidence')
    store=Store(retained/'pilot.sqlite3')
    try:evaluate(retained,store)
    finally:store.close()
    result=consolidate([retained,fresh],out,'16家银行合并',allow_agreement=True,coverage=run.get('coverage',[]))
    save(out/'replacement-provenance.json',dict(base=str(base.resolve()),replacement=str(fresh.resolve()),banks=sorted(banks)))
    print({'source':str(out.resolve()),'offers':len(result['llm']['offers'])})


if __name__=='__main__':main()

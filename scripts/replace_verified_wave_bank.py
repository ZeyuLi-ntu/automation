"""Combine verified recapture with other banks; preserve both source attempts."""
import argparse,shutil
from pathlib import Path
from market_rates.common import load,save,digest
from market_rates.board_wave import validate_wave
from scripts.merge_board_waves import merge

def replace(base,fresh,out):
    base=Path(base);fresh=Path(fresh);out=Path(out)
    new=validate_wave(fresh);banks={s['bank'] for s in new['sections']}
    kept=out.with_name(out.name+'-kept');shutil.copytree(base,kept)
    r=load(kept/'run.json');proof=load(kept/'wave-checks.json')
    for key in ['pages','tasks','sections']:r[key]=[v for v in r[key] if v['bank'] not in banks]
    r['coverage']=[v for v in r.get('coverage',[]) if v['bank'] not in banks]
    r['task_hash']=digest(r['tasks']);r['evidence_hash']=digest(r['pages']);ids={t['id'] for t in r['tasks']}
    proof.update(task_hash=r['task_hash'],checks=[c for c in proof['checks'] if c['task'] in ids])
    save(kept/'run.json',r);save(kept/'wave-checks.json',proof);merge([kept,fresh],out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--fresh',required=True);p.add_argument('--out',required=True);a=p.parse_args();replace(a.base,a.fresh,a.out)

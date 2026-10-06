"""Replace explicitly re-captured bank evidence, then require a new full proof."""
import argparse,shutil
from pathlib import Path
from market_rates.common import load,save,digest
from market_rates.pipeline import evidence_index
from scripts.capture_board_repairs import attach_hsbc_audiences

def compose(base,replacement,out):
    base=Path(base);replacement=Path(replacement);out=Path(out);run=load(base/'run.json');new=load(replacement/'run.json')
    banks={s['bank'] for s in new['sections']};out.mkdir(parents=True,exist_ok=False);(out/'evidence').mkdir()
    for field in ['pages','sections','tasks']:run[field]=[v for v in run[field] if v['bank'] not in banks]+new[field]
    run.update(id=out.name,as_of=max(run['as_of'],new['as_of']),parents=[str(base.resolve()),str(replacement.resolve())]);run['bank_dates'].update(new['bank_dates'])
    for source in [base,replacement]:
        for f in (source/'evidence').iterdir():
            if f.is_file() and f.name!='index.html':shutil.copy2(f,out/'evidence'/f.name)
    attach_hsbc_audiences(run,out);run.update(evidence_hash=digest(run['pages']),task_hash=digest(run['tasks']))
    save(out/'run.json',run);evidence_index(run['pages'],out/'evidence')
    print('Composed',len(run['sections']),'sections;',len(run['tasks']),'tasks. Fresh verification required.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--replacement',required=True);p.add_argument('--out',required=True);a=p.parse_args();compose(a.base,a.replacement,a.out)

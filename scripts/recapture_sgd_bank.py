"""Refresh one bank's captured evidence, archiving originals before replacement."""
import argparse,shutil
from datetime import datetime
from pathlib import Path
from market_rates.common import load,save,digest
from market_rates.capture import capture_sources
from market_rates.pipeline import check_evidence,evidence_index

def recapture(root,bank):
    root=Path(root);run=load(root/'run.json');cfg=load(root/'config.snapshot.json');check_evidence(run,root/'evidence')
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S');fresh=root/('recapture-'+bank+'-'+stamp);fresh.mkdir()
    subset=dict(cfg,sources=[dict(s) for s in cfg['sources'] if s['bank']==bank],expected_banks=[bank])
    if bank=='UOB':
        for s in subset['sources']:
            if s.get('capture_units'):s['dismiss_selectors']=['.dy-custom-close-btn:visible']
    save(fresh/'config.snapshot.json',subset)
    pages,errors=capture_sources(subset,fresh/'evidence')
    if errors or not pages or any(not p['ok'] or not p['complete'] for p in pages):raise ValueError('Recapture incomplete: '+str(errors))
    backup=fresh/'before';backup.mkdir();shutil.copytree(root/'evidence',backup/'evidence')
    shutil.copy2(root/'run.json',backup/'run.json');shutil.copy2(root/'config.snapshot.json',backup/'config.snapshot.json')
    for f in (fresh/'evidence').iterdir():
        if not f.is_file() or f.name in ['index.html','capture.json']:continue
        dest=root/'evidence'/f.name
        if dest.exists():shutil.copy2(dest,backup/'evidence'/f.name)
        shutil.copy2(f,dest)
    for lane in ['llm','vlm']:
        path=root/f'model-{bank}-{lane}.json'
        if path.exists():path.rename(backup/path.name)
    run['pages']=[p for p in run['pages'] if p['bank']!=bank]+pages;run['evidence_hash']=digest(run['pages'])
    run.setdefault('recaptures',[]).append(dict(bank=bank,archive=str(backup.resolve()),at=stamp))
    cfg['sources']=[s for s in cfg['sources'] if s['bank']!=bank]+subset['sources']
    save(root/'config.snapshot.json',cfg);save(root/'run.json',run);check_evidence(run,root/'evidence');evidence_index(run['pages'],root/'evidence')
    print('Recaptured',bank,len(pages),'pages; originals preserved in',backup)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--bank',required=True);a=p.parse_args();recapture(a.run,a.bank)

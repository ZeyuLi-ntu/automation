"""Retry a failed bank only, preserving the failed capture in the audit ledger."""
import argparse
from pathlib import Path
from datetime import datetime, timezone
from market_rates.common import load, save, digest
from market_rates.capture import capture_sources
from market_rates.pipeline import check_evidence, evidence_index
p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--bank',required=True);a=p.parse_args()
root=Path(a.run);run=load(root/'run.json');cfg=load(root/'config.snapshot.json')
check_evidence(run,root/'evidence')
if any(p['bank']==a.bank for p in run['pages']):raise ValueError('Refusing to replace already captured bank evidence')
cfg['sources']=[s for s in cfg['sources'] if s['bank']==a.bank]
for s in cfg['sources']:s['settle_ms']=3000
temp=root/('retry-'+a.bank+'-'+datetime.now().strftime('%H%M%S'))
pages,errors=capture_sources(cfg,temp)
run.setdefault('capture_attempts',[]).append(dict(at=datetime.now(timezone.utc).isoformat(),bank=a.bank,previous_errors=run['errors'],retry_errors=errors))
if not errors and pages:
    for f in temp.iterdir():
        if f.name=='capture.json':continue
        target=root/'evidence'/f.name
        if target.exists():raise ValueError('Evidence collision')
        target.write_bytes(f.read_bytes())
    run['pages'].extend(pages);run['errors']=[e for e in run['errors'] if not e.startswith(a.bank+' ')]
    run['evidence_hash']=digest(run['pages'])
    save(root/'evidence'/'capture.json',dict(pages=run['pages'],errors=run['errors']))
    evidence_index(run['pages'],root/'evidence')
save(root/'run.json',run);print(dict(added_pages=len(pages),retry_errors=errors))

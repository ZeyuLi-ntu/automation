"""Rebind saved independent evidence, preserving all earlier extraction files."""
import argparse,shutil
from datetime import datetime
from pathlib import Path
from market_rates.common import load,save
from market_rates.sgd_source_alignment import align_tables
from market_rates.multi_bank_validation import matched_offers
from market_rates.pipeline import check_evidence,evaluate
from market_rates.store import Store

def apply(root):
    root=Path(root);run=load(root/'run.json');check_evidence(run,root/'evidence')
    backup=root/('alignment-before-'+datetime.now().strftime('%Y%m%d-%H%M%S'));backup.mkdir()
    shutil.copy2(root/'run.json',backup/'run.json')
    banks=load(root/'config.snapshot.json')['expected_banks'];run['metadata']=[]
    for lane in ['llm','vlm']:
        run[lane]=dict(offers=[],inventory=[],coverage_complete=True,unreadable=[])
        for bank in banks:
            path=root/f'model-{bank}-{lane}.json';value=load(path);shutil.copy2(path,backup/path.name)
            changes=align_tables(value['result']['offers'],value['metadata']['terms_transcripts'],[p for p in run['pages'] if p['bank']==bank],lane)
            value['metadata']['table_alignment']=changes;save(path,value)
            run['metadata'].append(value['metadata'])
            for field in ['offers','inventory','unreadable']:run[lane][field]+=value['result'][field]
            run[lane]['coverage_complete'] &= value['result']['coverage_complete']
    save(root/'run.json',run)
    store=Store(root/'pilot.sqlite3')
    try:evaluate(root,store)
    finally:store.close()
    good,bad=matched_offers(run);print('Aligned own evidence:',len(good),'matched; remaining differences:',bad)
    if bad:raise ValueError('Remaining independent differences')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);apply(p.parse_args().run)

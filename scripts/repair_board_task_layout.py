"""Retry failed literal transcriptions with row-shape hints, no supplied answers."""
import argparse,shutil,re
from pathlib import Path
from market_rates.common import load,save,digest

def repair(source,out):
    source=Path(source);out=Path(out);r=load(source/'run.json');proof=load(source/'wave-checks.json')
    failed={e['task'] for e in proof['errors']};out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(source/'evidence',out/'evidence')
    for task in r['tasks']:
        if task['id'] in failed and task['kind']=='grid':task['strict_row_layout']=True
        if task['kind']=='grid':task['merged_caption_rows']=[i for i,row in enumerate(task['expected']) if len(row)==1 and re.search(r'[A-Za-z]',row[0])]
        if task['bank']=='CIMB' and any(s.get('layout')=='cimb-sgd' and task['id'] in s['task_ids'] for s in r['sections']):
            task['comparison_profile']='cimb-sgd-dollar-sign'
    r['id']=out.name;r['task_hash']=digest(r['tasks']);r['layout_retry_source']=str(source.resolve())
    save(out/'run.json',r);return r

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--out',required=True);x=a.parse_args();repair(x.source,x.out)

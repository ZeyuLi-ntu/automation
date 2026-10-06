"""Retain failed source evidence and request a complete literal transcription."""
import argparse,shutil
from pathlib import Path
from datetime import datetime
from market_rates.common import load,save,digest

def retry(root):
    root=Path(root);run=load(root/'run.json');proof=load(root/'wave-checks.json')
    ids={x['task'] for x in proof['errors']}
    archive=root/('before-literal-retry-'+datetime.now().strftime('%H%M%S%f'));archive.mkdir()
    for name in ['run.json','wave-checks.json']:
        shutil.copy2(root/name,archive/name)
    for task in run['tasks']:
        if task['id'] in ids and task['kind']=='text':task['strict_literal_text']=True
    run['task_hash']=digest(run['tasks']);save(root/'run.json',run)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);retry(p.parse_args().run)

"""Recrop the clipped original PDF header; retain previous evidence and proof."""
import argparse,hashlib,shutil
from datetime import datetime
from pathlib import Path
import pymupdf
from market_rates.common import load,save,digest
from scripts.verify_board_wave import verify
from scripts.qualify_board_wave import qualify

def repair(root):
    root=Path(root).resolve();run=load(root/'run.json');stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    backup=root.parent/(root.name+'-before-header-'+stamp);shutil.copytree(root,backup)
    task=next(t for t in run['tasks'] if t['id']=='rhb-sgd-context')
    page=pymupdf.open(root/'evidence/rhb-source.pdf')[0];rect=pymupdf.Rect(60,132,700,181)
    name=task['images'][0];path=root/'evidence'/name
    page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=rect).save(path)
    task['expected']=page.get_text(clip=rect,sort=True).strip()
    sha=hashlib.sha256(path.read_bytes()).hexdigest();task['image_hashes'][name]=sha
    next(p for p in run['pages'] if p['id']==task['page_id'])['image_hashes'][name]=sha
    run['evidence_hash']=digest(run['pages']);run['task_hash']=digest(run['tasks'])
    run['header_repair']=dict(reason='Original crop clipped heading and date',previous=str(backup),source_pdf='rhb-source.pdf')
    save(root/'run.json',run);verify(root,load('config/project.local.json'))
    target=root.with_name(root.name+'-qualified')
    if target.exists():target.rename(root.parent/(target.name+'-before-header-'+stamp))
    qualify(root,target)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);repair(p.parse_args().run)

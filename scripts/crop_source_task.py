"""Retain an original evidence tile while removing an unrelated spanning cell."""
import argparse,hashlib,shutil,pymupdf
from pathlib import Path
from datetime import datetime
from market_rates.common import load,save,digest

def crop(root,tid,left):
    root=Path(root);run=load(root/'run.json');task=next(t for t in run['tasks'] if t['id']==tid)
    archive=root/('before-tile-crop-'+datetime.now().strftime('%H%M%S%f'));archive.mkdir()
    shutil.copy2(root/'run.json',archive/'run.json')
    pix=pymupdf.Pixmap(root/'evidence'/task['images'][0]);rect=pymupdf.IRect(left,0,pix.width,pix.height)
    clipped=pymupdf.Pixmap(pix.colorspace,rect,pix.alpha);clipped.copy(pix,rect)
    name=tid+'-own-cells.png';clipped.save(root/'evidence'/name)
    sha=hashlib.sha256((root/'evidence'/name).read_bytes()).hexdigest()
    task.update(images=[name],image_hashes={name:sha})
    page=next(p for p in run['pages'] if p['id']==task['page_id']);page['images'].append(name);page['image_hashes'][name]=sha
    run.update(task_hash=digest(run['tasks']),evidence_hash=digest(run['pages']));save(root/'run.json',run)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--task',required=True);p.add_argument('--left',required=True,type=int);a=p.parse_args();crop(a.run,a.task,a.left)

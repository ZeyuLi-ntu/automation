"""Split one original screenshot at reviewed cell boundaries; retain all pixels."""
import argparse, hashlib, shutil
from uuid import uuid4
from pathlib import Path
from datetime import datetime
import pymupdf
from market_rates.common import load, save, digest

def split(root, task_id, cuts):
    root = Path(root); run = load(root/'run.json')
    task = next(t for t in run['tasks'] if t['id'] == task_id)
    if len(task['images']) != 1 or len(task['expected']) != 1:
        raise ValueError('Requires one source image and one physical row')
    source = pymupdf.Pixmap(root/'evidence'/task['images'][0])
    bounds = [0, *cuts, source.width]
    if bounds != sorted(set(bounds)) or len(bounds)-1 != len(task['expected'][0]):
        raise ValueError('Cell boundaries do not match row')
    archive = root/('before-cell-split-'+datetime.now().strftime('%H%M%S%f')+'-'+uuid4().hex[:8])
    archive.mkdir(); shutil.copy2(root/'run.json',archive/'run.json')
    names=[]; hashes={}
    for index,(left,right) in enumerate(zip(bounds,bounds[1:])):
        rect=pymupdf.IRect(left,0,right,source.height)
        tile=pymupdf.Pixmap(source.colorspace,rect,source.alpha); tile.copy(source,rect)
        name=f'{task_id}-cell-{index}.png'; tile.save(root/'evidence'/name)
        names.append(name); hashes[name]=hashlib.sha256((root/'evidence'/name).read_bytes()).hexdigest()
    task.update(images=names,image_hashes=hashes,images_are_cells=True)
    page=next(p for p in run['pages'] if p['id']==task['page_id'])
    page['images']+=names; page['image_hashes'].update(hashes)
    run.update(task_hash=digest(run['tasks']),evidence_hash=digest(run['pages']))
    save(root/'run.json',run)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--task',required=True)
    p.add_argument('--cuts',required=True);a=p.parse_args()
    split(a.run,a.task,[int(v) for v in a.cuts.split(',')])

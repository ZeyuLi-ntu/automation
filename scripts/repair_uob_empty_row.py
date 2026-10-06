"""Use separate original-pixel cells for the very wide dash-only row."""
from pathlib import Path
import argparse,hashlib,pymupdf
from market_rates.common import load,save,digest
def repair(folder):
    folder=Path(folder);run=load(folder/'run.json');task=next(t for t in run['tasks'] if t['id'].endswith('CNH-47-physical-1'))
    image=folder/'evidence'/task['images'][0];pix=pymupdf.Pixmap(image);names=[];n=len(task['expected'][0])
    for i in range(n):
        rect=pymupdf.IRect(round(pix.width*i/n),0,round(pix.width*(i+1)/n),pix.height)
        cell=pymupdf.Pixmap(pix.colorspace,rect,pix.alpha);cell.copy(pix,rect)
        name=image.stem+'-cell'+str(i)+'.png';cell.save(folder/'evidence'/name);names.append(name)
    task['images']=names;task['images_are_cells']=True;task['image_hashes']={n:hashlib.sha256((folder/'evidence'/n).read_bytes()).hexdigest() for n in names}
    page=next(p for p in run['pages'] if p['id']==task['page_id']);page['images']+=names;page['image_hashes'].update(task['image_hashes'])
    run['task_hash']=digest(run['tasks']);run['evidence_hash']=digest(run['pages']);save(folder/'run.json',run)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);repair(p.parse_args().run)

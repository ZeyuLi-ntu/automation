"""Repair ambiguous image layout from original local PDF/pixels, without new rates."""
import argparse,hashlib,re,shutil
from datetime import datetime
from pathlib import Path
import pymupdf
from market_rates.common import load,save,digest

def repair(root):
    root=Path(root).resolve();stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    for bank in ['RHB','UOB']:
        folder=root/bank;run=load(folder/'run.json');shutil.copytree(folder,root/(bank+'-before-crop-'+stamp))
        if bank=='RHB':
            pdf=next((folder/'evidence').glob('*source.pdf'));doc=pymupdf.open(pdf)
            for task in run['tasks']:
                m=re.search(r'-p(\d+)-r(\d+)$',task['id'])
                if not m or not re.search(r'\([A-Z]{3}\)',task['expected'][0][0]):continue
                pg=doc[int(m[1])-1];table=pg.find_tables().tables[0];rect=pymupdf.Rect(table.rows[int(m[2])].bbox)
                first=task['expected'][0][0].split()[0];words=[w for w in pg.get_text('words',clip=rect) if w[4]==first]
                if len(words)!=1:raise ValueError('Ambiguous source currency position')
                rect.x0=words[0][0]-2;name=task['images'][0]
                pg.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=rect).save(folder/'evidence'/name)
        else:
            task=next(t for t in run['tasks'] if t['id'].endswith('CNH-47'))
            image=folder/'evidence'/task['images'][0];pix=pymupdf.Pixmap(image)
            if len(task['expected'])!=2:raise ValueError('Expected caption plus one data row')
            new=[]
            for i,row in enumerate(task['expected']):
                rect=pymupdf.IRect(0,0 if i==0 else pix.height//2,pix.width,pix.height//2 if i==0 else pix.height)
                crop=pymupdf.Pixmap(pix.colorspace,rect,pix.alpha);crop.copy(pix,rect)
                name=image.stem+'-physical-'+str(i)+'.png';crop.save(folder/'evidence'/name)
                item=dict(task,id=task['id']+'-physical-'+str(i),expected=[row],images=[name]);new.append(item)
            run['tasks']=[t for t in run['tasks'] if t is not task]+new
            for section in run['sections']:
                section['task_ids']=[x for tid in section['task_ids'] for x in ([t['id'] for t in new] if tid==task['id'] else [tid])]
            page=next(p for p in run['pages'] if p['id']==task['page_id']);page['images'] += [t['images'][0] for t in new]
        for task in run['tasks']:task['image_hashes']={n:hashlib.sha256((folder/'evidence'/n).read_bytes()).hexdigest() for n in task['images']}
        for page in run['pages']:page['image_hashes']={n:hashlib.sha256((folder/'evidence'/n).read_bytes()).hexdigest() for n in page['images']}
        run['task_hash']=digest(run['tasks']);run['evidence_hash']=digest(run['pages']);run['image_layout_repair']=str(root/(bank+'-before-crop-'+stamp));save(folder/'run.json',run)
        retry=root/(bank+'-layout-retry')
        if retry.exists():retry.rename(root/(bank+'-layout-retry-before-crop-'+stamp))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);repair(p.parse_args().run)

"""Repair source-pixel framing without replacing failed transcriptions."""
import argparse,shutil,hashlib,pymupdf
from pathlib import Path
from market_rates.common import load,save,digest
def repair(source,out):
    source=Path(source);out=Path(out);out.mkdir(parents=True,exist_ok=False);shutil.copytree(source/'evidence',out/'evidence');r=load(source/'run.json');proof=load(source/'wave-checks.json')
    failed={e['task'] for e in proof['errors']};removed={t['id'] for t in r['tasks'] if t['kind']=='text' and (not t['expected'].strip() or (t['bank']=='CITI' and 'All rates offered are promotional rates' in t['expected']))}
    r['tasks']=[t for t in r['tasks'] if t['id'] not in removed]
    for s in r['sections']:
        s['task_ids']=[i for i in s['task_ids'] if i not in removed];s['extra_evidence']=[e for e in s.get('extra_evidence',[]) if e['quote'].strip() and not (s['bank']=='CITI' and 'All rates offered are promotional rates' in e['quote'])]
    for t in r['tasks']:
        if t['kind']=='text' and 'terms' in t['id']:t['comparison_profile']='promo-terms'
        if t['id'] not in failed or 'terms' in t['id']:continue
        for old in t['images']:
            src=pymupdf.open(out/'evidence'/old);pix=src[0].get_pixmap();src.close();doc=pymupdf.open();pg=doc.new_page(width=pix.width+80,height=pix.height+80);pg.insert_image(pymupdf.Rect(40,40,pix.width+40,pix.height+40),pixmap=pix);pg.get_pixmap().save(out/'evidence'/old);doc.close()
            sha=hashlib.sha256((out/'evidence'/old).read_bytes()).hexdigest();t['image_hashes'][old]=sha
            for p in r['pages']:
                if old in p['image_hashes']:p['image_hashes'][old]=sha
    r.update(id=out.name,task_hash=digest(r['tasks']),evidence_hash=digest(r['pages']),repair_source=str(source.resolve()),removed_empty_tasks=sorted(removed));save(out/'run.json',r)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--source');a.add_argument('--out');x=a.parse_args();repair(x.source,x.out)

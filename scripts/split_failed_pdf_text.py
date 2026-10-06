"""Split failed PDF text evidence into small source-pixel word groups."""
import argparse,hashlib,re,shutil
from uuid import uuid4
from pathlib import Path
from datetime import datetime
import pymupdf
from market_rates.common import load,save,digest
from scripts.verify_board_wave import canonical_transcription

def split(root,task_ids=None):
    root=Path(root);run=load(root/'run.json');proof=load(root/'wave-checks.json')
    failed={x['task'] for x in proof['errors']};new=[];replacements={}
    if task_ids is not None:failed &= set(task_ids)
    archive=root/('before-pdf-split-'+datetime.now().strftime('%H%M%S%f')+'-'+uuid4().hex[:8]);archive.mkdir()
    for name in ['run.json','wave-checks.json']:shutil.copy2(root/name,archive/name)
    for task in run['tasks']:
        pdf=root/'evidence'/(task['page_id']+'.pdf')
        if task['id'] not in failed or task['kind']!='text' or not pdf.exists():new.append(task);continue
        doc=pymupdf.open(pdf);lines=task['expected'].splitlines();parts=[]
        for line in lines:
            words=line.split()
            if not words:continue
            matches=[]
            for pi,page in enumerate(doc):
                source=page.get_text('words',sort=True)
                for i in range(len(source)-len(words)+1):
                    if [w[4] for w in source[i:i+len(words)]]==words:matches.append((pi,source[i:i+len(words)]))
            if len(matches)!=1:raise ValueError('PDF line not uniquely located: '+line)
            pi,source=matches[0]
            for start in range(0,len(source),6):
                chunk=source[start:start+6];rect=pymupdf.Rect(chunk[0][:4])
                for word in chunk[1:]:rect|=pymupdf.Rect(word[:4])
                tid=task['id']+'-words-'+str(len(parts));name=tid+'.png'
                doc[pi].get_pixmap(matrix=pymupdf.Matrix(3,3),clip=rect+(-1,-1,1,1)).save(root/'evidence'/name)
                sha=hashlib.sha256((root/'evidence'/name).read_bytes()).hexdigest()
                piece=dict(task,id=tid,expected=' '.join(w[4] for w in chunk),images=[name],image_hashes={name:sha},strict_literal_text=True,auto_pdf_split=True)
                parts.append(piece)
                page=next(p for p in run['pages'] if p['id']==task['page_id']);page['images'].append(name);page['image_hashes'][name]=sha
        assert canonical_transcription(' '.join(p['expected'] for p in parts),task)==canonical_transcription(task['expected'],task)
        replacements[task['id']]=[p['id'] for p in parts];new.extend(parts);doc.close()
    for section in run['sections']:section['task_ids']=[j for i in section['task_ids'] for j in replacements.get(i,[i])]
    run.update(tasks=new,task_hash=digest(new),evidence_hash=digest(run['pages']));save(root/'run.json',run)
    print('Split source tasks:',len(replacements))
    return replacements

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);split(p.parse_args().run)

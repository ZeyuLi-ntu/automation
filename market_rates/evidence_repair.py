"""Bounded source-preserving repair; no guessed rates or equal-width cuts."""
import hashlib, shutil
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from .common import load,save,digest,confined


def source_cell_cuts(boxes,pixel_width):
    if len(boxes)<2 or any(not b or b['width']<=0 or b['height']<=0 for b in boxes):return None
    first=boxes[0];end=boxes[-1]['x']+boxes[-1]['width']
    for left,right in zip(boxes,boxes[1:]):
        if abs(left['x']+left['width']-right['x'])>1:return None
        if abs(right['y']-first['y'])>1 or abs(right['height']-first['height'])>1:return None
    scale=pixel_width/(end-first['x'])
    cuts=[round((b['x']-first['x'])*scale) for b in boxes[1:]]
    return cuts if [0,*cuts,pixel_width]==sorted(set([0,*cuts,pixel_width])) else None


def printed_grid_cuts(path,count):
    """Legacy evidence: accept only full-height printed rule edges, including shadows."""
    import pymupdf
    pix=pymupdf.Pixmap(path)
    if pix.colorspace!=pymupdf.csRGB:pix=pymupdf.Pixmap(pymupdf.csRGB,pix)
    if count<2 or pix.height<12:return None
    data=pix.samples;stride=pix.stride;n=pix.n
    ys=list(range(max(2,pix.height//10),pix.height-max(2,pix.height//10)))
    columns=[]
    for x in range(2,pix.width-2):
        hits=0
        for y in ys:
            rgb=data[y*stride+x*n:y*stride+x*n+3]
            before=data[y*stride+(x-1)*n:y*stride+(x-1)*n+3]
            if max(rgb)-min(rgb)<=5 and 100<=min(rgb)<=242 and min(before)-max(rgb)>=12:hits+=1
        if hits>=len(ys)*.97:columns.append(x)
    groups=[]
    for x in columns:
        if groups and x==groups[-1][-1]+1:groups[-1].append(x)
        else:groups.append([x])
    # A border's falling edge precedes its shadow. Accept only an exact count;
    # never invent equal columns or choose a subset of ambiguous lines.
    if len(groups)!=count-1 or any(len(g)>4 for g in groups):return None
    cuts=[g[len(g)//2] for g in groups]
    return cuts if min(b-a for a,b in zip([0,*cuts],[*cuts,pix.width]))>=16 else None


def eligible(error):
    text=str(error).lower()
    return any(s in text for s in ['literal source/transcription mismatch','token repeat limit',
                                  'incomplete model response','expecting value','expecting delimiter',
                                  'expecting property name','unterminated string'])


def repair(root,stage):
    root=Path(root);run=load(root/'run.json');proof=load(root/'wave-checks.json')
    if proof['task_hash']!=digest(run['tasks']):raise ValueError('修复停止：核验记录与当前来源不匹配')
    tasks={t['id']:t for t in run['tasks']};failed={e['task'] for e in proof['errors'] if eligible(e.get('error',''))}
    for tid in failed:
        task=tasks[tid]
        for name,sha in task['image_hashes'].items():
            if hashlib.sha256(confined(root/'evidence',name).read_bytes()).hexdigest()!=sha:
                raise ValueError('修复停止：原始证据已变化')
    actions=[];unresolved=[]
    archive=root/('auto-repair-original-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+uuid4().hex[:8])
    archive.mkdir()
    for name in ['run.json','wave-checks.json']:shutil.copy2(root/name,archive/name)
    for tid in failed:
        for lane in ['llm','vlm']:
            for prefix in ['raw-','mismatch-']:
                path=confined(root,prefix+tid+'-'+lane+'.json')
                if path.exists():shutil.copy2(path,archive/path.name)
    for tid in sorted(failed):
        task=tasks[tid]
        if stage=='layout':
            if task['kind']=='grid' and any(e['task']==tid and 'token repeat limit' in e.get('error','').lower() for e in proof['errors']):
                continue # Wide empty rows need smaller source tiles, not the same image again.
            flag='strict_row_layout' if task['kind']=='grid' else 'strict_literal_text'
            if not task.get(flag):
                task[flag]=True;actions.append(dict(task=tid,method='明确表格行列结构' if task['kind']=='grid' else '逐字完整转录'))
        elif task['kind']=='grid' and len(task['expected'])==1 and len(task['images'])==1 and not task.get('images_are_cells'):
            name=task['images'][0];image=confined(root/'evidence',name)
            cuts=task.get('source_cell_cuts') if task.get('source_geometry_image_hash')==task['image_hashes'][name] else None
            method='原网页单元格位置拆图'
            if cuts is None:
                cuts=printed_grid_cuts(image,len(task['expected'][0]));method='原图清晰表格线拆图'
            if cuts is None:
                unresolved.append(dict(task=tid,reason='单元格边界不明确，未猜测切图'));continue
            # Persist strict flags before helper archives/splits this task.
            run.update(task_hash=digest(run['tasks']));save(root/'run.json',run)
            from scripts.split_source_row_cells import split
            split(root,tid,cuts)
            run=load(root/'run.json');tasks={t['id']:t for t in run['tasks']}
            actions.append(dict(task=tid,method=method))
    run.update(task_hash=digest(run['tasks']));save(root/'run.json',run)
    if stage=='source':
        from scripts.split_failed_pdf_text import split
        for tid in sorted(failed):
            task=tasks[tid]
            if task['kind']!='text' or task.get('auto_pdf_split'):continue
            if not confined(root/'evidence',task['page_id']+'.pdf').exists():continue
            try:
                changed=split(root,[tid])
                if changed:actions.append(dict(task=tid,method='原PDF文字坐标分段截图'))
            except ValueError as exc:
                unresolved.append(dict(task=tid,reason=str(exc)))
    return dict(stage=stage,actions=actions,unresolved=unresolved,archive=str(archive))

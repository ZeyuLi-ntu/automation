"""Publish an explicit verified subset only under the user's partial-output rule."""
import argparse,shutil,struct
from pathlib import Path
from market_rates.common import load,save,digest

def qualify(source,out):
    source=Path(source);out=Path(out);run=load(source/'run.json');proof=load(source/'wave-checks.json')
    if proof['task_hash']!=run['task_hash']:raise ValueError('Proof/source mismatch')
    tasks={t['id']:t for t in run['tasks']};passed={(c['task'],c['lane']) for c in proof['checks'] if c['passed'] and c['task_hash']==digest(tasks[c['task']])}
    sections=[];held=list(run.get('coverage',[]));accessibility=[]
    for section in run['sections']:
        # This caption is a 1-CSS-pixel screen-reader label, not printed table
        # content. Preserve its metadata, but do not pretend VLM can read it.
        invisible=[]
        for tid in section['task_ids']:
            t=tasks[tid]
            if section['bank']=='Singapura Finance' and t['expected']==[['Fixed deposit interest rates by tenure and deposit size']] and len(t['images'])==1:
                dims=struct.unpack('>II',(source/'evidence'/t['images'][0]).read_bytes()[16:24])
                if max(dims)<=2:invisible.append(tid);accessibility.append(dict(task=tid,reason='2×2像素的屏幕阅读器专用caption，不属于可见金融字段'))
        section=dict(section,task_ids=[t for t in section['task_ids'] if t not in invisible])
        missing=[t for t in section['task_ids'] if any((t,l) not in passed for l in ['llm','vlm'])]
        if missing:
            from market_rates.board_wave import SCB_FX,CIMB_FX
            cur=section['currency']
            if cur=='FX' and section['bank']=='SCB':cur=SCB_FX[section['table']]
            if cur=='FX' and section['bank']=='CIMB':cur=CIMB_FX[section['table']]
            held.append(dict(bank=section['bank'],currency=cur,product_id=section['product_id'],section=section['id'],reason='文字/视觉转录仍有差异；本轮不插数值',failed_tasks=missing,numeric_insertion=False))
        else:sections.append(section)
    capture_errors=list(run.get('errors',[]))
    held += [dict(bank=e.get('bank','来源采集'),source=e.get('source'),reason='采集未完成；本轮不插数值：'+str(e.get('error','未知原因')),numeric_insertion=False) for e in capture_errors]
    required={t for s in sections for t in s['task_ids']}
    if not sections:raise ValueError('No complete verified section')
    shutil.copytree(source,out);run.update(id=out.name,sections=sections,tasks=[t for t in run['tasks'] if t['id'] in required],coverage=held,errors=[],qualification_capture_errors=capture_errors,qualification_source=str(source.resolve()),partial_output_authorization='用户2026-09-28：暂保留待核，先输出已核实部分')
    run['task_hash']=digest(run['tasks']);run['non_visual_metadata']=accessibility;checks=[c for c in proof['checks'] if c['task'] in required]
    save(out/'full-attempt-checks.json',proof);save(out/'run.json',run)
    save(out/'wave-checks.json',dict(passed=True,task_hash=run['task_hash'],checks=checks,errors=[],scope='explicit qualified subset; failed sections listed in coverage'))
    print(dict(qualified_sections=len(sections),held=held),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--run',required=True);a.add_argument('--out',required=True);args=a.parse_args();qualify(args.run,args.out)

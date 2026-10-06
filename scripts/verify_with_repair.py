"""One local bounded recovery entry point for board and FX literal verification."""
import argparse
from pathlib import Path
from datetime import datetime
from market_rates.common import load,save
from market_rates.evidence_repair import repair
from scripts.verify_board_wave import verify,VerificationMismatch


def report(root,state):
    save(root/'automatic-repair.json',state)
    lines=['本地识别自动修复：'+{'running':'正在处理','complete':'核对通过','needs_review':'仍有未解决项','error':'来源或运行环境异常'}[state['status']]]
    for event in state['attempts']:
        lines += [a['task']+'：'+a['method'] for a in event.get('actions',[])]
        lines += [u['task']+'：'+u['reason'] for u in event.get('unresolved',[])]
    for item in state.get('remaining',[]):lines.append(item['task']+'：'+item.get('error','未通过'))
    if state['status'] in ['error','needs_review']:
        lines+=['未把识别错误当作正确报价。已保留原图与日志。',
                '网络或模型服务恢复后可双击“继续上次全量任务.cmd”。',
                '同一图片持续失败时，请提供本目录的 automatic-repair.json、wave-checks.json 和 evidence 原图。']
    if state.get('error'):lines.append(state['error'])
    (root/'自动修复结果.txt').write_text('\n'.join(lines),encoding='utf-8-sig')


def check(root,config):
    root=Path(root)
    previous=load(root/'automatic-repair.json') if (root/'automatic-repair.json').exists() else {}
    state=dict(status='running',source_root=str(root.resolve()),started_at=datetime.now().isoformat(),attempts=previous.get('attempts',[]),local_only=True)
    report(root,state)
    stages=iter(['layout','source'])
    try:
        while True:
            try:
                verify(root,config)
                state.update(status='complete',remaining=[],finished_at=datetime.now().isoformat());report(root,state)
                print('本地核对通过；自动修复记录：'+str(root/'自动修复结果.txt'),flush=True)
                return
            except VerificationMismatch as exc:
                state['remaining']=load(root/'wave-checks.json')['errors']
                changed=False
                for stage in stages:
                    event=repair(root,stage);state['attempts'].append(event);report(root,state)
                    if event['actions']:
                        print('本地自动修复：'+'；'.join(a['task']+' '+a['method'] for a in event['actions']),flush=True)
                        changed=True;break
                if not changed:
                    state.update(status='needs_review',finished_at=datetime.now().isoformat());report(root,state)
                    print('自动修复后仍未通过，原证据已保留。查看：'+str(root/'自动修复结果.txt'),flush=True)
                    raise exc
    except Exception as exc:
        if state['status']!='needs_review':
            state.update(status='error',error=str(exc));report(root,state)
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--config',default='config/project.local.json')
    a=p.parse_args();check(a.run,load(a.config))

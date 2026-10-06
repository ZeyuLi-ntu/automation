"""Collect local recognition repair outcomes into a user-readable run summary."""
from pathlib import Path
from .common import load

def write_summary(work):
    work=Path(work).resolve();reports={}
    for path in sorted(work.rglob('automatic-repair.json')):
        state=load(path);source=Path(state.get('source_root',str(path.parent))).resolve()
        try:source.relative_to(work)
        except ValueError:continue
        reports[str(source)]=(state,source)
    lines=['本次本地识别自动修复汇总',str(work),'']
    if not reports:lines+=['本次尚未进入挂牌／外币促销的自动识别修复步骤；此处没有记录不代表任务已完成。']
    for state,source in reports.values():
        actions=[a for e in state.get('attempts',[]) for a in e.get('actions',[])]
        label={'complete':'修复后通过' if actions else '直接核对通过','needs_review':'仍需处理','error':'来源或环境异常','running':'处理中'}.get(state['status'],state['status'])
        lines+=[str(source.relative_to(work))+'：'+label]
        lines += ['  '+a['task']+'：'+a['method'] for a in actions]
        lines += ['  '+e['task']+'：'+e.get('error','未通过') for e in state.get('remaining',[])]
        if state['status']!='complete':lines+=['  详情：'+str(source/'自动修复结果.txt')]
    lines+=['','仅重新识别原始证据，不推测、补写或放宽利率数值。',
            '暂时性服务问题可双击“继续上次全量任务.cmd”；持续无法辨认的图片需要进一步处理。',
            '此汇总目前覆盖挂牌和外币促销的表格核验；新元促销使用独立提取流程，其错误仍见主任务日志。']
    target=work/'识别修复汇总.txt';target.write_text('\n'.join(lines),encoding='utf-8-sig')
    return target

"""Local board-pilot capture/replay, native Excel copies, and round-trip validation."""
from datetime import datetime
from pathlib import Path
import argparse,json,os,subprocess,sys,webbrowser
from market_rates.common import load,save
from market_rates.board_plan import make_plan,ROOT

def runtimes():
    config=ROOT/'config/runtime.local.json'
    if not config.exists():raise ValueError('请先在 config/runtime.local.json 配置本地 Node、表格工具和验证 Python 路径。')
    values=load(config)
    for key in ['node','node_modules','validation_python']:
        if not Path(values[key]).exists():raise ValueError('Missing local runtime: '+key)
    return values
def main():
    p=argparse.ArgumentParser();p.add_argument('--fresh',action='store_true');p.add_argument('--run');p.add_argument('--base-output');p.add_argument('--no-open',action='store_true');a=p.parse_args()
    os.chdir(ROOT);runtime=runtimes();stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f');state=dict(status='running',completed=[])
    out=ROOT/'outputs'/('board-pilot-'+stamp)
    def execute(args,env=None):subprocess.run(args,cwd=ROOT,env=env,check=True)
    try:
        if a.fresh:
            if a.run:raise ValueError('Fresh capture cannot overwrite an existing run')
            run=ROOT/'runs'/('board-pilot-'+stamp)
            execute([sys.executable,'-X','utf8','-m','scripts.capture_board_pilot','--out',str(run)])
            execute([sys.executable,'-X','utf8','-m','scripts.extract_board_pilot','--run',str(run)])
        else:
            run=Path(a.run) if a.run else Path(load(ROOT/'outputs/latest-board-pilot.json')['source_run'])
        state.update(source_run=str(run.resolve()),output=str(out));base=load(Path(a.base_output)/'table-validation-plan.json') if a.base_output else None
        plan=make_plan(run,out,base);state['completed'].append('核验与插表映射');save(out/'workflow.json',state)
        env=dict(os.environ,MARKET_NODE_MODULES=runtime['node_modules'],PSModulePath='')
        execute([runtime['node'],'scripts/build_board_inputs.mjs',str(out)],env)
        execute(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/write_board_excel.ps1','-PlanPath',str(out/'table-validation-plan.json')],env)
        state['completed'].append('Excel副本');save(out/'workflow.json',state)
        execute([runtime['validation_python'],'-X','utf8','-m','scripts.check_board_excel','--output',str(out)],env)
        state.update(status='complete',completed=state['completed']+['保存后回读验证']);save(out/'workflow.json',state)
        save(ROOT/'outputs/latest-board-pilot.json',dict(output=str(out),source_run=str(run.resolve()),human_reviewed=False))
        if not a.no_open:webbrowser.open((out/'table-validation.html').as_uri())
        print('挂牌试点验证副本已生成：'+str(out),flush=True)
    except Exception as exc:
        state.update(status='failed',error=str(exc));save(ROOT/'data/board-workflow-last-error.json',state)
        if out.exists():save(out/'workflow.json',state)
        raise
if __name__=='__main__':main()

"""Replay verified local batch into native Excel copies; publish pointer after QA."""
import argparse,os,subprocess,sys,webbrowser
from pathlib import Path
from datetime import datetime
from market_rates.common import load,save
from market_rates.board_batch_plan import plan,ROOT
from scripts.run_board_workflow import runtimes

def main():
    a=argparse.ArgumentParser();a.add_argument('--run');a.add_argument('--base-output');a.add_argument('--no-open',action='store_true');args=a.parse_args();os.chdir(ROOT)
    latest=load(ROOT/'outputs/latest-board-pilot.json');source=Path(args.run or latest['source_run']);base=load(Path(args.base_output or latest['output'])/'table-validation-plan.json')
    out=ROOT/'outputs'/('board-batch-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));state=dict(status='running',source_run=str(source.resolve()),output=str(out),completed=[])
    try:
        p=plan(source,out,base);save(out/'workflow.json',state);rt=runtimes();env=dict(os.environ,MARKET_NODE_MODULES=rt['node_modules'],PSModulePath='')
        for label,cmd in [('报价输入',[rt['node'],'scripts/build_board_inputs.mjs',str(out)]),('Excel副本',['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/write_board_batch.ps1','-PlanPath',str(out/'table-validation-plan.json')]),('保存后回读',[rt['validation_python'],'-X','utf8','-m','scripts.check_board_batch','--output',str(out)])]:
            subprocess.run(cmd,env=env,cwd=ROOT,check=True);state['completed'].append(label);save(out/'workflow.json',state)
        state['status']='complete';save(out/'workflow.json',state);save(ROOT/'outputs/latest-board-pilot.json',dict(output=str(out),source_run=str(source.resolve()),human_reviewed=False))
        if not args.no_open:webbrowser.open((out/'table-validation.html').as_uri())
        print('挂牌扩展副本已生成：'+str(out),flush=True)
    except Exception as e:
        state.update(status='failed',error=str(e));save(ROOT/'data/board-batch-last-error.json',state)
        if out.exists():save(out/'workflow.json',state)
        raise
if __name__=='__main__':main()

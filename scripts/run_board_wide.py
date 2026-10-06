"""One local replay entry point for the wide board batch."""
import argparse,os,subprocess,webbrowser
from pathlib import Path
from datetime import datetime
from market_rates.common import load,save
from market_rates.board_wide_plan import plan,ROOT
from scripts.run_board_workflow import runtimes
from market_rates.table_validation import sha

def main():
    a=argparse.ArgumentParser();a.add_argument('--run');a.add_argument('--base-output');a.add_argument('--resume');a.add_argument('--no-open',action='store_true');args=a.parse_args();os.chdir(ROOT)
    if args.resume:
        out=Path(args.resume).resolve();state=load(out/'workflow.json');p=load(out/'table-validation-plan.json');source=Path(state['source_run'])
        if sha(source/'run.json')!=p['run_sha256']:raise ValueError('Source changed since interrupted board run')
        for kind in ['report','rainbow']:
            if sha(p[kind+'_template'])!=p[kind+'_sha256']:raise ValueError('Template changed since interrupted board run')
    else:
        latest=load(ROOT/'outputs/latest-board-pilot.json');source=Path(args.run or latest['source_run']);base=load(Path(args.base_output or latest['output'])/'table-validation-plan.json')
        out=ROOT/'outputs'/('board-wide-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));state=dict(status='running',source_run=str(source.resolve()),output=str(out),completed=[])
    try:
        if not args.resume:plan(source,out,base)
        state['status']='running';state.pop('error',None);save(out/'workflow.json',state);rt=runtimes();env=dict(os.environ,MARKET_NODE_MODULES=rt['node_modules'],PSModulePath='')
        for label,cmd in [('报价输入',[rt['node'],'scripts/build_board_inputs.mjs',str(out)]),('Excel副本',['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/write_board_wide.ps1','-PlanPath',str(out/'table-validation-plan.json')]),('保存后回读',[rt['validation_python'],'-X','utf8','-m','scripts.check_board_wide','--output',str(out)])]:
            if label not in state['completed']:
                subprocess.run(cmd,env=env,cwd=ROOT,check=True);state['completed'].append(label);save(out/'workflow.json',state)
        from scripts.finalize_board_rows import finalize
        if '合并同金额行及重建增幅公式' not in state['completed']:
            finalize(out);state['completed'].append('合并同金额行及重建增幅公式');save(out/'workflow.json',state)
        coverage=load(out/'board-coverage.json')
        coverage_summary={k:coverage[k] for k in ['required_count','pairs_with_numeric_output','missing_or_fully_held','required_pair_availability_complete']}
        state.update(status='complete',coverage=coverage_summary);save(out/'workflow.json',state);save(ROOT/'outputs/latest-board-pilot.json',dict(output=str(out),source_run=str(source.resolve()),human_reviewed=False,coverage=coverage_summary))
        if not args.no_open:webbrowser.open((out/'table-validation.html').as_uri())
        print('挂牌批量扩展已生成：'+str(out),flush=True)
        print('挂牌范围：'+str(coverage['pairs_with_numeric_output'])+'/'+str(coverage['required_count'])+' 个要求组合有本期数值；缺 '+str(coverage['missing_or_fully_held'])+' 个。',flush=True)
    except Exception as e:
        state.update(status='failed',error=str(e));save(ROOT/'data/board-wide-last-error.json',state)
        if out.exists():save(out/'workflow.json',state)
        raise
if __name__=='__main__':main()

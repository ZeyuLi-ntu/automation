"""Resumeable local refresh of the five repaired board-rate adapters."""
import argparse,os,subprocess,sys
from datetime import datetime
from pathlib import Path
from market_rates.common import load,save
from market_rates.board_wave import replace_verified_sections
from scripts.qualify_board_wave import qualify

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--resume');parser.add_argument('--no-open',action='store_true');args=parser.parse_args();os.chdir(ROOT)
    root=Path(args.resume).resolve() if args.resume else ROOT/'runs'/('board-repair-workflow-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    manifest=root/'workflow.json'
    if args.resume:state=load(manifest)
    else:
        root.mkdir();latest=load(ROOT/'outputs/latest-board-pilot.json')
        state=dict(status='running',completed=[],base_run=latest['source_run'],base_output=latest['output']);save(manifest,state)
    def step(name,module,*argv,allow_failure=False):
        if name in state['completed']:return
        result=subprocess.run([sys.executable,'-X','utf8','-m',module,*map(str,argv)],cwd=ROOT)
        if result.returncode and not allow_failure:raise RuntimeError(name+'失败；上次输出保留')
        state['completed'].append(name);save(manifest,state)
    try:
        step('发现来源','scripts.probe_board_repairs','--out',root/'discovery')
        step('冻结证据','scripts.capture_board_repairs','--discovery',root/'discovery','--out',root/'capture')
        step('本地双路核验','scripts.verify_with_repair','--run',root/'capture',allow_failure=True)
        if '筛选完整核验范围' not in state['completed']:
            qualify(root/'capture',root/'qualified');state['completed'].append('筛选完整核验范围');save(manifest,state)
        if '更新本期来源' not in state['completed']:
            replace_verified_sections(state['base_run'],root/'qualified',root/'combined');state['completed'].append('更新本期来源');save(manifest,state)
        step('生成并回读工作簿','scripts.run_board_wide','--run',root/'combined','--base-output',state['base_output'],*(['--no-open'] if args.no_open else []))
        state['status']='complete';save(manifest,state)
    except Exception as exc:
        state.update(status='failed',error=str(exc));save(manifest,state);raise

if __name__=='__main__':main()

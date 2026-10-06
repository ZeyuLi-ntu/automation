"""Collect all implemented board adapters locally, then publish only after QA."""
import argparse,subprocess,sys,os
from pathlib import Path
from datetime import datetime
from market_rates.common import load,save
from market_rates.board_batch import merge
from market_rates.board_wave import combine,replace_verified_sections
from scripts.merge_board_waves import merge as merge_waves
from market_rates.board_freshness import reconcile_run_dates
from scripts.qualify_board_wave import qualify
ROOT=Path(__file__).resolve().parents[1]

def main():
    a=argparse.ArgumentParser();a.add_argument('--resume');a.add_argument('--no-open',action='store_true');a.add_argument('--base-output');a.add_argument('--work-dir');args=a.parse_args();os.chdir(ROOT)
    folder=Path(args.resume).resolve() if args.resume else Path(args.work_dir).resolve() if args.work_dir else ROOT/'runs'/('board-bulk-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    manifest=folder/'workflow.json'
    if args.resume:state=load(manifest)
    else:
        folder.mkdir();state=dict(status='running',completed=[],base_output=load(ROOT/'outputs/latest-board-pilot.json')['output'],paths={k:str(folder/k) for k in ['discovery','pilot','expansion','legacy','wave','extra','wave-qualified','extra-qualified','repairs','repairs-qualified','ocbc','ocbc-qualified','icbc-hlf','icbc-hlf-qualified','remaining','remaining-verified','combined-initial','combined']});save(manifest,state)
    paths=state['paths']
    if args.base_output and not args.resume:
        state['previous_board_output']=state['base_output'];state['base_output']=str(Path(args.base_output).resolve());save(manifest,state)
    def step(name,module,*argv,allow_failure=False):
        if name in state['completed']:return
        result=subprocess.run([sys.executable,'-X','utf8','-m',module,*argv],cwd=ROOT)
        if result.returncode and not allow_failure:raise RuntimeError(name+'失败；原输出保留，查看 '+str(manifest))
        state['completed'].append(name);save(manifest,state)
    try:
        step('来源清单','scripts.probe_board_all','--out',paths['discovery'])
        step('HLB/SBI采集','scripts.capture_board_pilot','--out',paths['pilot'])
        step('HLB/SBI核验','scripts.extract_board_pilot','--run',paths['pilot'])
        step('BOC/HLB采集','scripts.capture_board_batch','--out',paths['expansion'])
        step('BOC/HLB核验','scripts.extract_board_batch','--run',paths['expansion'])
        if '基础合并' not in state['completed']:merge(paths['pilot'],paths['expansion'],paths['legacy']);state['completed'].append('基础合并');save(manifest,state)
        modern='repairs' in paths # Resuming an older manifest keeps its original stages.
        flags=['--modern-sources'] if modern else []
        step('新增银行采集','scripts.capture_board_wave','--discovery',paths['discovery'],'--out',paths['wave'],*flags,*(['--ocbc-modern'] if 'ocbc' in paths else []),*(['--icbc-hlf-modern'] if 'icbc-hlf' in paths else []))
        step('附件弹窗采集','scripts.capture_board_additions','--discovery',paths['discovery'],'--out',paths['extra'],*flags,*(['--icbc-hlf-modern'] if 'icbc-hlf' in paths else []))
        if modern:step('动态页面和定存附件','scripts.capture_board_repairs','--discovery',paths['discovery'],'--out',paths['repairs'])
        if 'ocbc' in paths:step('OCBC全币种挂牌','scripts.capture_ocbc_board','--out',paths['ocbc'])
        if 'icbc-hlf' in paths:step('工行三币种及HLF挂牌','scripts.capture_icbc_hlf_board','--out',paths['icbc-hlf'])
        keys=['wave','extra']+(['repairs'] if modern else [])+(['ocbc'] if 'ocbc' in paths else [])+(['icbc-hlf'] if 'icbc-hlf' in paths else [])
        subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/start_local_model.ps1'],check=True,cwd=ROOT)
        for key in keys:
            step(key+'核验','scripts.verify_with_repair','--run',paths[key],allow_failure=True)
            # Partial output was explicitly approved by the user. Every enrolled
            # section still requires both complete source-matching lanes.
            if key+'已核实范围' not in state['completed']:
                qualify(paths[key],paths[key+'-qualified']);state['completed'].append(key+'已核实范围');save(manifest,state)
        if 'remaining' in paths:
            step('剩余六家挂牌采集','scripts.capture_remaining_board','--out',paths['remaining'])
            step('剩余六家本地核验','scripts.verify_remaining_board','--run',paths['remaining'])
        if '全批合并' not in state['completed']:
            initial=paths.get('combined-initial',paths['combined'])
            if not (Path(initial)/'run.json').exists():combine(paths['legacy'],[paths[k+'-qualified'] for k in keys],initial)
            if 'remaining' in paths:
                results=load(Path(paths['remaining'])/'verification-summary.json')
                if len(results)!=6 or not all(r['passed'] for r in results):raise ValueError('六家本地核验未全部完成')
                if not (Path(paths['remaining-verified'])/'run.json').exists():merge_waves([r['path'] for r in results],paths['remaining-verified'])
                if not (Path(paths['combined'])/'run.json').exists():replace_verified_sections(initial,paths['remaining-verified'],paths['combined'])
            state['completed'].append('全批合并');save(manifest,state)
        if 'remaining' in paths and '与上次银行日期比较' not in state['completed']:
            prior=load(Path(state.get('previous_board_output',state['base_output']))/'table-validation-plan.json')['source_run']
            reconcile_run_dates(prior,paths['combined']);state['completed'].append('与上次银行日期比较');save(manifest,state)
        build_args=['--run',paths['combined'],'--base-output',state['base_output']]
        error=ROOT/'data/board-wide-last-error.json'
        if error.exists():
            failed=load(error);attempt=Path(failed['output'])/'table-validation-plan.json'
            if attempt.exists():
                previous=load(attempt)
                if Path(failed['source_run']).resolve()==Path(paths['combined']).resolve() and Path(previous.get('base_output','')).resolve()==Path(state['base_output']).resolve():
                    build_args=['--resume',failed['output']]
        step('生成并验证','scripts.run_board_wide',*build_args,*(['--no-open'] if args.no_open else []))
        state.update(status='complete',output=load(ROOT/'outputs/latest-board-pilot.json')['output'],source_run=paths['combined']);save(manifest,state);print('批处理完成：'+str(manifest))
    except Exception as exc:
        state.update(status='failed',error=str(exc));save(manifest,state);raise

if __name__=='__main__':main()

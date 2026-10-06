"""One local entry: SGD promotions -> all boards -> FX promotions -> two files."""
import argparse,contextlib,json,os,subprocess,sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from market_rates.common import load,save
from market_rates.table_validation import sha
from scripts.run_board_workflow import runtimes

ROOT=Path(__file__).resolve().parents[1]
FX_BANKS=['BEA','BOC','CIMB','CITI','DBS','HSBC','ICBC','RHB','SBI','SCB']

@contextlib.contextmanager
def project_lock():
    import msvcrt
    path=ROOT/'data/unified-run.lock';path.parent.mkdir(exist_ok=True)
    with path.open('a+b') as f:
        f.seek(0);f.write(b'1');f.flush();f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise RuntimeError('已有全量任务正在运行，请使用已有窗口查看进度。')
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)

def preflight():
    rt=runtimes();cfg=load(ROOT/'config/project.local.json');model=cfg['models']
    if model.get('provider')!='ollama' or urlsplit(model.get('base_url','')).hostname not in ['127.0.0.1','localhost','::1']:
        raise ValueError('全量入口只允许本机Ollama，不调用云端模型。')
    paths={'python':Path(sys.executable),'node':Path(rt['node']),'node_modules':Path(rt['node_modules']),
           'validation_python':Path(rt['validation_python']),'bank_links':ROOT.parent/'利率链接.xlsx'}
    ollama=load(ROOT/'config/ollama.runtime.local.json')
    paths.update(ollama=Path(ollama['binary']),models=Path(ollama['model_directory']))
    for name,path in paths.items():
        if not path.exists():raise ValueError('本机依赖缺失：'+name+' '+str(path))
    import pymupdf
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);browser.close()
    subprocess.run(['powershell','-NoProfile','-Command',"$e=New-Object -ComObject Excel.Application; try {$e.Visible=$false; $e.Version} finally {$e.Quit(); [Runtime.InteropServices.Marshal]::FinalReleaseComObject($e)|Out-Null}"],check=True,capture_output=True)
    return dict(passed=True,local_only=True,requires_codex_running=False,model=model['text_model'],paths={k:str(v) for k,v in paths.items()})

def seeds():
    sgd=load(ROOT/'outputs/latest-workflow.json');board=load(ROOT/'outputs/latest-board-pilot.json');fx=load(ROOT/'outputs/latest-fx-promo.json')
    sp=load(Path(sgd['output'])/'table-validation-plan.json')
    return dict(sgd_output=sgd['output'],sgd_source=sp['source_run'],board_source=board['source_run'],board_output=board['output'],fx_source=fx['source_run'],final_output=fx['output'])

def run(args):
    os.chdir(ROOT)
    with project_lock():
        if args.check:
            result=preflight();save(ROOT/'data/standalone-check.json',result);print('本机依赖检查通过：浏览器、Excel、Python、Node、本地模型文件均可用；不需要Codex保持打开。');return
        if args.resume:
            work=Path(args.resume).resolve();state=load(work/'workflow.json')
            if state['project']!=str(ROOT):raise ValueError('不是本项目的工作流')
            args.mode=state['mode']
            if state['status']=='complete':
                print('任务已经完成：'+state['output'])
                if not args.no_open:os.startfile(state['report'])
                return
        else:
            work=ROOT/'runs'/('all-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));work.mkdir()
            selected=seeds()
            from market_rates.input_workbooks import configuration,prepare_selected_inputs
            inputs=configuration()
            if inputs['mode']=='selected':selected['final_output']=prepare_selected_inputs(work,inputs)
            state=dict(project=str(ROOT),mode=args.mode,status='running',completed=[],seeds=selected,input_selection=inputs,results={},started_at=datetime.now().isoformat())
        manifest=work/'workflow.json';save(manifest,state)
        save(ROOT/'outputs/latest-all-run.json',dict(workflow=str(work),status=state['status']))
        env=dict(os.environ,PYTHONUTF8='1',OLLAMA_NO_CLOUD='1',PSModulePath='')
        seed=state['seeds'];results=state['results']
        def command(key,module,*argv):
            cmd=[sys.executable,'-X','utf8','-m',module,*map(str,argv)]
            print('\n'+key,flush=True)
            with (work/(key+'.log')).open('a',encoding='utf8') as log:
                process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
                for line in process.stdout:log.write(line);log.flush();print(line.rstrip(),flush=True)
                code=process.wait()
            if code:raise RuntimeError(key+'失败，详情：'+str(work/(key+'.log')))
        def stage(key,fn):
            if key in state['completed']:return
            state.update(stage=key,status='running');save(manifest,state)
            fn();state['completed'].append(key);save(manifest,state)
        try:
            stage('本机依赖检查',lambda:save(work/'preflight.json',preflight()))
            def sgd():
                folder=work/'sgd';receipt=work/'sgd-result.json'
                argv=['--mode',args.mode,'--no-open','--receipt',receipt]
                if (folder/'workflow.json').exists():argv+=['--resume',folder]
                else:
                    argv+=['--work-dir',folder,'--template-output',seed['final_output'],'--template-current']
                    if args.mode=='rebuild':argv+=['--source-run',seed['sgd_source']]
                command('01新元促销','scripts.run_market_workflow',*argv)
                results['sgd']=load(receipt)
            stage('新元促销',sgd)
            def board():
                if args.mode=='rebuild':
                    argv=['--resume',results['board_attempt']] if results.get('board_attempt') else ['--run',seed['board_source'],'--base-output',results['sgd']['output']]
                    try:command('02全部挂牌','scripts.run_board_wide',*argv,'--no-open')
                    except Exception:
                        error=ROOT/'data/board-wide-last-error.json'
                        if error.exists():
                            failed=load(error);attempt=load(Path(failed['output'])/'table-validation-plan.json')
                            if Path(failed['source_run']).resolve()==Path(seed['board_source']).resolve() and Path(attempt.get('base_output','')).resolve()==Path(results['sgd']['output']).resolve():results['board_attempt']=failed['output']
                        raise
                    result=load(ROOT/'outputs/latest-board-pilot.json')
                    results.pop('board_attempt',None)
                else:
                    folder=work/'board';argv=['--no-open']
                    argv+=['--resume',folder] if (folder/'workflow.json').exists() else ['--work-dir',folder,'--base-output',results['sgd']['output']]
                    command('02全部挂牌','scripts.run_board_bulk',*argv);result=load(folder/'workflow.json')
                results['board']={k:result[k] for k in ['output','source_run']}
            stage('全部挂牌',board)
            def capture_fx():
                root=work/'fx-capture'
                for bank in FX_BANKS:
                    folder=root/bank
                    command('03外币采集-'+bank,'scripts.capture_fx_promo','--out',root,'--banks',bank)
                    command('03外币核验-'+bank,'scripts.verify_fx_wave','--run',folder)
                combined=work/'fx-combined'
                if combined.exists():
                    combined.rename(work/('fx-combined-attempt-'+datetime.now().strftime('%H%M%S%f')))
                command('03外币汇总','scripts.prepare_fx_run','--waves',*[root/b for b in FX_BANKS],'--out',combined,'--board',results['board']['source_run'])
                results['fx_source']=str(combined)
            if args.mode=='live':stage('外币促销采集',capture_fx)
            else:results['fx_source']=seed['fx_source']
            def fx():
                command('04外币促销插表','scripts.run_fx_promo','--run',results['fx_source'],'--base-output',results['board']['output'],'--no-open')
                results['fx']=load(ROOT/'outputs/latest-fx-promo.json')
            stage('外币促销插表',fx)
            p=load(Path(results['fx']['output'])/'table-validation-plan.json')
            from market_rates.sgd_comparison import check_saved
            stage('新元增幅检查',lambda:save(work/'sgd-comparison.json',check_saved(p['report_output'])))
            source_dates={key:load(Path(results[key]['source_run'])/'run.json')['as_of'] for key in ['sgd','board']}
            source_dates['fx']=load(Path(results['fx_source'])/'run.json')['as_of']
            state.update(status='complete',finished_at=datetime.now().isoformat(),output=results['fx']['output'],source_dates=source_dates,
                         report=p['report_output'],rainbow=p['rainbow_output'],output_hashes={k:sha(p[k+'_output']) for k in ['report','rainbow']})
            state.pop('error',None)
            save(manifest,state);save(ROOT/'outputs/latest-all.json',dict(workflow=str(work),output=state['output'],mode=args.mode,source_dates=source_dates))
            save(ROOT/'outputs/latest-all-run.json',dict(workflow=str(work),status='complete'))
            print('\n三部分已合并为同一套调研和彩虹表：'+state['output'],flush=True)
            print('各部分资料日期：'+json.dumps(source_dates,ensure_ascii=False)+'；重建不会伪装成重新采集。',flush=True)
            if not args.no_open:os.startfile(p['report_output'])
        except Exception as exc:
            state.update(status='failed',error=str(exc));save(manifest,state)
            save(ROOT/'outputs/latest-all-run.json',dict(workflow=str(work),status='failed'))
            print('任务已保存进度。双击“继续上次全量任务.cmd”重试失败步骤；已完成结果不需重跑。',file=sys.stderr)
            raise
        finally:
            try:
                from market_rates.repair_feedback import write_summary
                print('识别修复汇总：'+str(write_summary(work)),flush=True)
            except Exception as feedback_error:
                print('识别汇总未生成；原始银行日志仍保留：'+str(feedback_error),file=sys.stderr)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['live','rebuild'],default='live');p.add_argument('--resume');p.add_argument('--check',action='store_true');p.add_argument('--no-open',action='store_true');run(p.parse_args())

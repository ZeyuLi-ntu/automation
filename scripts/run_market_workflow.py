"""Local, resumable bank draft workflow with human-approved weekly baselines."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import webbrowser
import shutil
from market_rates.common import load,save
from market_rates.consolidate import consolidate
from market_rates.multi_bank_validation import plan_multi
from market_rates.table_validation import sha
from market_rates.weekly_history import baseline
from market_rates.workbook_policy import bank_in_scope

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['live','rebuild'],default='live')
    p.add_argument('--resume',help='继续上次工作流目录，不重新采集成功批次')
    p.add_argument('--no-open',action='store_true')
    p.add_argument('--source-run',help='重建指定已验证的新元促销批次')
    p.add_argument('--template-output',help='明确传入本次流程底稿，避免读取错误的独立入口指针')
    p.add_argument('--template-current',action='store_true',help='在最新完整工作簿中更新SGD，保留其他部分全部历史')
    p.add_argument('--work-dir')
    p.add_argument('--receipt')
    a=p.parse_args();os.chdir(ROOT)
    runtime=Path(os.environ.get('MARKET_RUNTIME',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies')))
    read_python=runtime/'python/python.exe';node=runtime/'node/bin/node.exe'
    poppler=runtime/'native/poppler/Library/bin/pdftoppm.exe'
    for path in [read_python,node,poppler]:
        if not path.exists():raise ValueError('未找到已配置运行环境：'+str(path))
    env=dict(os.environ,MARKET_NODE_MODULES=str(runtime/'node/node_modules'),PYTHONUTF8='1')
    env={k:v for k,v in env.items() if k.casefold()!='psmodulepath'}
    pins=load(ROOT/'config/validated-batches.json')
    for template in pins.get('templates',[]):
        if sha(ROOT/template['path'])!=template['sha256']:raise ValueError('模板或行映射已变化，请重新核验：'+template['path'])
    if a.resume:
        work=Path(a.resume).resolve();manifest=load(work/'workflow.json')
        if manifest['project']!=str(ROOT):raise ValueError('工作流不属于本项目')
        a.mode=manifest['mode']
    else:
        work=Path(a.work_dir).resolve() if a.work_dir else ROOT/'runs'/('workflow-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));work.mkdir()
        manifest=dict(project=str(ROOT),mode=a.mode,completed=[],status='running',sources=[],source_run=a.source_run,template_output=a.template_output,template_current=a.template_current)
    a.source_run=manifest.get('source_run');a.template_output=manifest.get('template_output')
    a.template_current=manifest.get('template_current',False)
    if a.source_run and a.mode!='rebuild':raise ValueError('冻结源仅用于重建，不用于重新采集')
    state=work/'workflow.json';save(state,manifest)
    def command(args,name,allowed=(0,)):
        print(name,flush=True)
        if name=='模型检查':
            # The persistent Ollama child may retain PowerShell's output handle.
            # Wait for the starter process, not EOF on its inherited pipe.
            with (work/(name+'.log')).open('a',encoding='utf8') as log:
                code=subprocess.run([str(x) for x in args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
            print((work/(name+'.log')).read_text(encoding='utf8',errors='replace'),flush=True)
            if code not in allowed:raise RuntimeError(name+'失败，详情见 '+str(work/(name+'.log')))
            return
        with (work/(name+'.log')).open('a',encoding='utf8') as log:
            process=subprocess.Popen([str(x) for x in args],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
            for line in process.stdout:print(line.rstrip(),flush=True);log.write(line);log.flush()
            code=process.wait()
        if code not in allowed:raise RuntimeError(name+'失败，详情见 '+str(work/(name+'.log')))
    def stage(key,fn):
        if key in manifest['completed']:return
        manifest.update(status='running',stage=key);save(state,manifest);fn()
        manifest['completed'].append(key);save(state,manifest)
    try:
        if a.mode=='live':
            # A resumed job must check the service again even if a prior starter
            # completed; that persistent process may have stopped meanwhile.
            command(['powershell','-NoProfile','-File','scripts/start_local_model.ps1'],'模型检查')
            source_folders=[]
            for key,module in [('SCB','scripts.run_scb_pilot'),('RHB-CIMB-HLF','scripts.run_three_bank_pilot'),('OCBC-HLB-SBI','scripts.run_next_bank_pilot'),('UOB-ICBC-BOC','scripts.run_expansion_bank_pilot')]:
                folder=work/key;source_folders.append(str(folder))
                def collect(folder=folder,module=module,key=key):
                    args=[sys.executable,'-X','utf8','-m',module,'--out',folder]
                    if (folder/'run.json').exists():args+=['--resume']
                    command(args,key+'采集与验证')
                stage(key,collect)
            from market_rates.remaining_banks import BANKS
            for bank in BANKS:
                folder=work/('remaining-'+bank.replace(' ','-'));source_folders.append(str(folder))
                def collect_remaining(folder=folder,bank=bank):
                    if folder.exists() and (not (folder/'run.json').exists() or any(not e.startswith('TERMS_REVIEW:') for e in load(folder/'run.json').get('errors',[]))):
                        folder.resolve().relative_to(work.resolve())
                        archived=work/(folder.name+'-failed-'+datetime.now().strftime('%H%M%S%f'))
                        archived.resolve().relative_to(work.resolve())
                        folder.rename(archived)
                    args=[sys.executable,'-X','utf8','-m','scripts.run_remaining_bank_pilot','--bank',bank,'--out',folder]
                    if (folder/'run.json').exists():args+=['--resume']
                    command(args,bank+'采集与验证')
                stage(bank,collect_remaining)
            public=work/'public-status'
            stage('公开来源状态',lambda:command([sys.executable,'-X','utf8','-m','scripts.collect_public_status','--out',public],'公开来源状态'))
            from market_rates.coverage_status import public_inventory
            coverage=public_inventory(public)
        elif a.source_run:
            from market_rates.pipeline import check_evidence
            source=Path(a.source_run).resolve();run=load(source/'run.json');check_evidence(run,source/'evidence')
            source_folders=[str(source)];coverage=run.get('coverage',[])
        else:
            source_folders=[]
            for item in pins['sources']:
                folder=ROOT/item['path']
                if any(sha(folder/name)!=value for name,value in item['hashes'].items()):raise ValueError('已验证批次发生变化，请重新核验：'+str(folder))
                source_folders.append(str(folder))
            coverage=[c for c in pins.get('coverage',[]) if bank_in_scope(c['bank'])]
        manifest['sources']=source_folders;save(state,manifest)
        combined=Path(a.source_run).resolve() if a.source_run else work/'combined'
        out=ROOT/'outputs'/(work.parent.name+'-'+work.name if work.parent.name.startswith('all-') else work.name)
        def merge():
            if combined.exists():
                # An interrupted merge is task-owned; archive it, never delete or
                # silently reuse a partially written run.
                combined.resolve().relative_to(work.resolve())
                if combined.resolve().parent!=work.resolve():raise ValueError('合并归档路径越界')
                destination=work/('combined-attempt-'+datetime.now().strftime('%H%M%S%f'))
                destination.resolve().relative_to(work.resolve());combined.rename(destination)
            count=sum(len(load(Path(f)/'config.snapshot.json')['expected_banks']) for f in source_folders)
            consolidate(source_folders,combined,str(count)+'家银行合并',allow_agreement=a.mode=='live',coverage=coverage)
        stage('合并银行',lambda:None if a.source_run else merge())
        def choose_baseline():
            approved=baseline(ROOT)
            manifest['approved_baseline']=approved
            manifest['report_template']=approved['report'] if approved else str(ROOT.parent/'20260916市场利率调研.xlsx')
            manifest['rainbow_template']=approved['rainbow'] if approved else str(ROOT.parent/'彩虹表_按MarketRateData更新_20260916_17.59.xlsx')
            if a.template_output:
                chosen=load(Path(a.template_output)/'table-validation-plan.json')
                key='template' if a.source_run and not a.template_current else 'output'
                for kind in ['report','rainbow']:manifest[kind+'_template']=chosen[kind+'_'+key]
                if key=='output':
                    board=chosen['base_plan'] if chosen.get('kind')=='fx-promo' else str(Path(a.template_output)/'table-validation-plan.json') if chosen.get('kind')=='board-wide' else chosen.get('inherited_board_plan')
                    manifest['inherited_board_plan']=board
                    manifest['unified_predecessor']=a.template_output
        stage('选择已确认底稿',choose_baseline)
        if a.template_current and not manifest.get('template_snapshots'):
            copies=work/'templates';copies.mkdir(exist_ok=True);sources={}
            for kind in ['report','rainbow']:
                origin=Path(manifest[kind+'_template']);target=copies/(kind+'.xlsx');before=sha(origin)
                shutil.copy2(origin,target)
                if sha(target)!=before or sha(origin)!=before:raise ValueError('底稿在复制期间改变，请重试')
                sources[kind]=dict(path=str(origin),sha256=before);manifest[kind+'_template']=str(target)
            manifest['template_snapshots']=sources;save(state,manifest)
            # An interrupted generation may already have a plan; only the
            # identical immutable template path changes, not its contents.
            existing=out/'table-validation-plan.json'
            if existing.exists():
                planned=load(existing)
                for kind in ['report','rainbow']:planned[kind+'_template']=manifest[kind+'_template']
                save(existing,planned)
        inspection=work/'template-inspection.json'
        stage('检查底稿布局',lambda:command([read_python,'-X','utf8','-m','scripts.inspect_weekly_templates','--report',manifest['report_template'],'--rainbow',manifest['rainbow_template'],'--out',inspection],'读取实际历史布局'))
        stage('插表计划',lambda:plan_multi(combined,manifest['report_template'],manifest['rainbow_template'],inspection,out,approved=manifest.get('approved_baseline')))
        plan=out/'table-validation-plan.json'
        if manifest.get('inherited_board_plan'):
            planned=load(plan);planned['inherited_board_plan']=manifest['inherited_board_plan'];planned['unified_predecessor']=manifest.get('unified_predecessor');save(plan,planned)
        stage('输入明细',lambda:command([node,'scripts/build_validation_inputs.mjs',out],'生成输入明细'))
        stage('生成Excel',lambda:command(['powershell','-NoProfile','-File','scripts/validate_three_bank_excel.ps1','-PlanPath',plan,'-Retry'],'生成Excel副本'))
        def precheck():
            command([read_python,'-X','utf8','-m','scripts.check_three_bank_validation','--plan',plan],'保存文件检查',(0,1))
            checks=load(out/'table-validation-checks.json')
            failed=[c['name'] for c in checks['checks'] if not c['passed'] and c['name']!='原表有效样式保持']
            if failed:raise ValueError('插表检查未通过：'+str(failed))
        stage('文件初检',precheck)
        stage('历史样式',lambda:command(['powershell','-NoProfile','-File','scripts/check_native_styles.ps1','-PlanPath',plan],'历史样式检查'))
        stage('补充期限预览',lambda:command(['powershell','-NoProfile','-File','scripts/render_weekly_supplement.ps1','-PlanPath',plan],'补充期限预览'))
        def render():
            for pdf in out.glob('*-*.pdf'):command([poppler,'-png','-scale-to','1800','-singlefile',pdf,pdf.with_suffix('')],'预览-'+pdf.stem)
        stage('生成预览',render)
        stage('最终检查',lambda:command([read_python,'-X','utf8','-m','scripts.check_three_bank_validation','--plan',plan],'最终文件检查'))
        manifest.update(status='complete',output=str(out),review_status='pending_human_review');save(state,manifest)
        save(ROOT/'outputs/latest-workflow.json',dict(workflow=str(work),output=str(out),mode=a.mode))
        if a.receipt:save(a.receipt,dict(workflow=str(work),output=str(out),source_run=str(combined),mode=a.mode))
        print('新元促销已生成：'+str(out)+'\n可继续合并挂牌和外币促销；正式历史底稿未推进。',flush=True)
        if not a.no_open:webbrowser.open((out/'table-validation.html').as_uri())
    except Exception as exc:
        manifest.update(status='failed',error=str(exc));save(state,manifest)
        print('已停止，保留证据和日志。修复后使用 -Resume "'+str(work)+'" 继续。\n'+str(exc),file=sys.stderr)
        raise

if __name__=='__main__':main()

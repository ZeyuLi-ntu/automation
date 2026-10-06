"""Regenerate this captured FX batch locally, including persistent user corrections."""
import argparse,os,subprocess,webbrowser
from pathlib import Path
from datetime import datetime
from market_rates.common import load,save
from market_rates.fx_promo_plan import plan
from market_rates.board_wave import validate_wave
from market_rates.pipeline import check_evidence
from scripts.run_board_workflow import runtimes,ROOT
def main():
    a=argparse.ArgumentParser();a.add_argument('--run');a.add_argument('--base-output');a.add_argument('--no-open',action='store_true');x=a.parse_args();os.chdir(ROOT)
    latest=load(ROOT/'outputs/latest-fx-promo.json') if (ROOT/'outputs/latest-fx-promo.json').exists() else {}
    source=Path(x.run or latest['source_run']);run=load(source/'run.json');check_evidence(run,source/'evidence')
    for wave in run['fx_sources']:validate_wave(wave)
    if x.base_output:base=load(Path(x.base_output)/'table-validation-plan.json')
    else:base=load(load(Path(latest['output'])/'table-validation-plan.json')['base_plan'])
    if base.get('kind')!='board-wide':raise ValueError('使用包含本期挂牌和SGD促销的底稿')
    predecessor=base.get('unified_predecessor') or latest.get('output')
    if predecessor:
        from market_rates.history_dates import check_dates
        previous=load(Path(predecessor)/'table-validation-plan.json')
        check_dates(previous['report_output'],base['report_output'])
    out=ROOT/'outputs'/('fx-promo-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));p=plan(source,out,base);rt=runtimes();env=dict(os.environ,MARKET_NODE_MODULES=rt['node_modules'],PSModulePath='')
    state=dict(status='running',source_run=str(source.resolve()),output=str(out),completed=[]);save(out/'workflow.json',state)
    for label,cmd in [('报价输入',[rt['node'],'scripts/build_fx_inputs.mjs',str(out)]),('Excel插表',['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/write_fx_promo.ps1','-PlanPath',str(out/'table-validation-plan.json')]),('保存回读',[rt['validation_python'],'-X','utf8','-m','scripts.check_fx_promo','--out',str(out)])]:
        subprocess.run(cmd,cwd=ROOT,env=env,check=True);state['completed'].append(label);save(out/'workflow.json',state)
    state['status']='complete';save(out/'workflow.json',state);save(ROOT/'outputs/latest-fx-promo.json',dict(output=str(out),source_run=str(source.resolve()),human_reviewed=False))
    if not x.no_open:os.startfile(p['report_output'])
    print('外币促销已重新生成；使用本批保存证据，不调用模型API。'+str(out))
if __name__=='__main__':main()

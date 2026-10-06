"""Narrow repair of comparison formulas; keep every quoted rate and history cell."""
from pathlib import Path
from datetime import datetime
import os,subprocess,shutil,re
from market_rates.common import load,save
from market_rates.xlsx_read import merged_ranges
from market_rates.table_validation import sha
from scripts.run_board_workflow import runtimes,ROOT

def main():
    os.chdir(ROOT);latest=load(ROOT/'outputs/latest-fx-promo.json');base=Path(latest['output']);p=load(base/'table-validation-plan.json')
    out=ROOT/'outputs'/('rate-changes-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));out.mkdir()
    sources={k:p[k+'_output'] for k in ['report','rainbow']};hashes={k:sha(v) for k,v in sources.items()}
    source=out/'source-report.xlsx';shutil.copy2(sources['report'],source)
    p.update(output=str(out),correction_of=str(base),correction_source=str(source),correction_sha256=hashes['report'])
    for kind in ['report','rainbow']:p[kind+'_output']=str(out/(p['as_of'].replace('-','')+'_增幅修正_'+('调研' if kind=='report' else '彩虹表')+'.xlsx'))
    shutil.copy2(sources['rainbow'],p['rainbow_output'])
    merges=merged_ranges(source);p['correction_bank_merges']=[]
    for name in ['SGD促销','USD促销','CNY促销','其他外币促销利率','USD挂牌','CNY挂牌']:
        c='A' if name=='SGD促销' or name.startswith('CNY') else 'B'
        p['correction_bank_merges'].append(dict(sheet=name,ranges=[a for a in merges[name] if re.fullmatch(c+r'\d+:'+c+r'\d+',a)]))
    save(out/'table-validation-plan.json',p)
    subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/write_rate_change_corrections.ps1','-PlanPath',str(out/'table-validation-plan.json')],check=True,env=dict(os.environ,PSModulePath=''))
    subprocess.run([runtimes()['validation_python'],'-X','utf8','-m','scripts.check_rate_change_corrections','--out',str(out)],check=True)
    for kind,path in sources.items():assert sha(path)==hashes[kind]
    prior=load(ROOT/'outputs/latest-all.json')
    state=dict(project=str(ROOT),status='complete',mode='correction',output=str(out),report=p['report_output'],rainbow=p['rainbow_output'],source_workflow=prior['workflow'],source_dates=prior['source_dates'],output_hashes={k:sha(p[k+'_output']) for k in ['report','rainbow']})
    save(out/'workflow.json',state);save(ROOT/'outputs/latest-fx-promo.json',dict(latest,output=str(out)))
    save(ROOT/'outputs/latest-all.json',dict(workflow=str(out),output=str(out),mode='correction',source_dates=state['source_dates']))
    save(ROOT/'outputs/latest-all-run.json',dict(workflow=str(out),status='complete'))
    print('增幅修正完成：'+str(out),flush=True)
if __name__=='__main__':main()

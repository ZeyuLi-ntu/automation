"""Package a checked SGD correction while retaining the complete FX/board plan."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
from market_rates.common import load,save
from market_rates.table_validation import sha
from market_rates.xlsx_read import read_xlsx

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sgd-output',required=True)
    parser.add_argument('--base-output',required=True)
    args=parser.parse_args()
    sgd=Path(args.sgd_output).resolve();base=Path(args.base_output).resolve()
    checks=load(sgd/'table-validation-checks.json')
    if checks['passed']!=checks['total']:raise ValueError('SGD correction checks incomplete')
    plan=load(sgd/'table-validation-plan.json');p=load(base/'table-validation-plan.json')
    if p.get('kind')!='fx-promo':raise ValueError('Expected a complete FX/board predecessor')
    if plan['date_column_shift']!=0:raise ValueError('This correction must refresh the same date')
    evidence=[]
    report=read_xlsx(plan['report_output']);rainbow=read_xlsx(plan['rainbow_output'])
    for g in plan['groups']:
        if g['bank']!='BOC':continue
        r=g['report_row'];value=report['SGD促销']['C'+str(r)]
        if abs(float(value)-float(g['main_pct'])/100)>1e-10:raise ValueError('Reference rate missing: '+g['id'])
        for i,d in enumerate(g['details']):
            if d.get('reference_quote'):
                caption=report['SGD促销']['B'+str(r+i)]
                if d['valid_to'] not in caption or '最新公开参考' not in caption:raise ValueError('Reference notice missing')
        evidence.append(dict(group=g['id'],rate_pct=g['main_pct'],row=r))
    if not evidence:raise ValueError('BOC quotation not restored')
    out=ROOT/'outputs'/('latest-publication-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));out.mkdir()
    hashes={k:sha(plan[k+'_output']) for k in ['report','rainbow']}
    for kind,caption in [('report','调研'),('rainbow','彩虹表')]:
        target=out/(plan['as_of'].replace('-','')+'_最新公告补齐_'+caption+'.xlsx')
        shutil.copy2(plan[kind+'_output'],target)
        if sha(target)!=hashes[kind]:raise ValueError('Copy hash mismatch')
        p[kind+'_output']=str(target)
    p.update(output=str(out),correction_of=str(base),sgd_correction_plan=str(sgd/'table-validation-plan.json'),
             correction_kind='latest_publication_reference',correction_checks=str(sgd/'table-validation-checks.json'))
    save(out/'table-validation-plan.json',p)
    previous=load(ROOT/'outputs/latest-all.json');latest_fx=load(ROOT/'outputs/latest-fx-promo.json')
    state=dict(project=str(ROOT),status='complete',mode='correction',output=str(out),report=p['report_output'],
               rainbow=p['rainbow_output'],source_workflow=previous['workflow'],source_dates=previous['source_dates'],
               output_hashes=hashes,reference_groups=evidence,sgd_correction=str(sgd))
    save(out/'workflow.json',state)
    save(ROOT/'outputs/latest-fx-promo.json',dict(latest_fx,output=str(out)))
    save(ROOT/'outputs/latest-all.json',dict(workflow=str(out),output=str(out),mode='correction',source_dates=state['source_dates']))
    save(ROOT/'outputs/latest-all-run.json',dict(workflow=str(out),status='complete'))
    print(str(out),flush=True)


if __name__=='__main__':main()

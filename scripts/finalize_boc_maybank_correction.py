"""Publish only checked local correction copies and retain their provenance."""
import argparse
from pathlib import Path
from datetime import datetime
import shutil
from market_rates.common import load,save
from market_rates.table_validation import sha
from scripts.check_boc_maybank_correction import check
from market_rates.sgd_comparison import check_saved

ROOT=Path(__file__).resolve().parents[1]


def main():
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--sgd-output',required=True);x=a.parse_args()
    source=Path(x.output).resolve();sgd=Path(x.sgd_output).resolve()
    sgd_checks=load(sgd/'table-validation-checks.json')
    if sgd_checks['passed']!=sgd_checks['total']:raise ValueError('Incomplete SGD checks')
    if load(source/'workflow.json')['status']!='complete':raise ValueError('Incomplete FX workflow')
    p=load(source/'table-validation-plan.json');bp=load(p['base_plan'])
    if load(Path(p['base_plan']).parent/'workflow.json')['status']!='complete':raise ValueError('Incomplete board workflow')
    result=check(source,sgd);comparison=check_saved(p['report_output'])
    original=ROOT.parent/'20260930市场利率调研_1.xlsx'
    original_hash='013e2c8f47751d27bc9c9545871bed1dbdb16ecd73d06d80efbad18d4ba9d493'
    if sha(original)!=original_hash:raise ValueError('Original input changed; retain correction without publishing latest pointer')
    out=ROOT/'outputs'/('boc-maybank-corrected-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));out.mkdir()
    for kind,label in [('report','调研'),('rainbow','彩虹表')]:
        target=out/('20261001_中行挂牌及Maybank修正_'+label+'.xlsx')
        shutil.copy2(p[kind+'_output'],target)
        if sha(target)!=result[kind+'_sha256']:raise ValueError('Copy hash mismatch')
        p[kind+'_output']=str(target)
    p.update(output=str(out),correction_kind='boc_board_references_maybank_standalone',
             correction_source=str(source),sgd_correction_plan=str(sgd/'table-validation-plan.json'))
    save(out/'table-validation-plan.json',p);save(out/'boc-maybank-correction-checks.json',result)
    save(out/'sgd-comparison.json',comparison)
    sp=load(sgd/'table-validation-plan.json');dates=dict(sgd=sp['as_of'],board=bp['as_of'],fx=p['as_of'])
    previous=load(ROOT/'outputs/latest-all.json')
    state=dict(project=str(ROOT),status='complete',mode='correction',output=str(out),
               report=p['report_output'],rainbow=p['rainbow_output'],source_workflow=previous['workflow'],source_dates=dates,
               output_hashes={k:sha(p[k+'_output']) for k in ['report','rainbow']},original_input=str(original),original_sha256=original_hash,
               results=dict(sgd=dict(output=str(sgd),source_run=sp['source_run']),board=dict(output=str(Path(p['base_plan']).parent),source_run=bp['source_run']),
                            fx=dict(output=str(out),source_run=p['source_run']),fx_source=p['source_run']))
    save(out/'workflow.json',state)
    (out/'修正说明.txt').write_text('本次在本机完成采集、识别、Excel 插表和保存检查。\n中行：官网最新挂牌公告仍为2026-06-22；9个币种已核对并改为引用挂牌全批明细。\nMaybank：只取第ii部分Standalone定存，20,000新元起存；6/9/12个月分别1.85%/1.80%/1.85%。\nMaybank证据日期2026-10-01；其他银行沿用2026-09-30批次核验资料，详情保留各自来源日期。\n原始输入文件未修改。今后统一入口会自动使用已修正采集与插表规则。\n',encoding='utf8')
    save(ROOT/'outputs/latest-fx-promo.json',dict(output=str(out),source_run=p['source_run'],human_reviewed=False))
    save(ROOT/'outputs/latest-all.json',dict(workflow=str(out),output=str(out),mode='correction',source_dates=dates))
    save(ROOT/'outputs/latest-all-run.json',dict(workflow=str(out),status='complete'))
    print(str(out))


if __name__=='__main__':main()

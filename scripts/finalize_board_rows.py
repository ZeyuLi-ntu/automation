"""Apply the user's compact board layout after native board validation."""
import argparse,subprocess
from pathlib import Path
from market_rates.common import load,save
from market_rates.board_cleanup import plan
from scripts.check_board_cleanup import check

def finalize(out):
    out=Path(out).resolve();base=load(out/'table-validation-plan.json')
    cleanup_dir=out/'row-cleanup';cleanup_dir.mkdir(exist_ok=True)
    p=plan(base['report_output'],cleanup_dir)
    target=out/(Path(base['report_output']).stem+'_合并金额行.xlsx')
    # A saved cleanup copy can survive an interrupted final readback. Only
    # reuse it if the full current plan reconciles every retained observation.
    reusable=False
    if target.exists():
        try:check(cleanup_dir/'board-cleanup-plan.json',target);reusable=True
        except AssertionError:pass
    if not reusable:
        subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','scripts/write_board_cleanup.ps1','-PlanPath',str(cleanup_dir/'board-cleanup-plan.json'),'-ReportOutput',str(target)],check=True)
    result=check(cleanup_dir/'board-cleanup-plan.json',target)
    # Keep the pre-compaction mapping for the checks already run. A later run
    # reads row limits from this final plan and actual labels from the workbook.
    save(out/'pre-cleanup-plan.json',base)
    base['pre_cleanup_report']=base['report_output'];base['report_output']=str(target)
    base['cleanup_plan']=str(cleanup_dir/'board-cleanup-plan.json')
    for h in base['histories']:
        fix=next(s for s in p['sheets'] if s['sheet']==h['sheet']);h['max_row']-=len(fix['delete_rows'])
    for m in base['matrices']:
        if m['sheet']=='SGD挂牌':m['end']-=len(p['cimb_sgd']['delete_rows'])
    save(out/'table-validation-plan.json',base)
    # The user-facing link must open the compact final workbook.
    html=out/'table-validation.html'
    if html.exists():html.write_text(html.read_text(encoding='utf8').replace(Path(base['pre_cleanup_report']).name,target.name),encoding='utf8')
    return result

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);finalize(a.parse_args().out)

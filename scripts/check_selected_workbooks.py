"""Exercise a real selected template pair without changing settings or outputs."""
from datetime import datetime
from pathlib import Path
import shutil
from market_rates.common import load,save
from market_rates.input_workbooks import CONFIG,save_configuration,prepare_selected_inputs
from market_rates.table_validation import sha
from market_rates.weekly_history import baseline
from market_rates.board_wide_plan import plan as board_plan
from market_rates.multi_bank_validation import plan_multi
from scripts.inspect_weekly_templates import inspect
from scripts.run_all import seeds,ROOT

def check():
    work=ROOT/'runs'/('input-selection-check-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));work.mkdir()
    seed=seeds();p=load(Path(seed['final_output'])/'table-validation-plan.json')
    config_hash=sha(CONFIG);hashes={k:sha(p[k+'_output']) for k in ['report','rainbow']}
    a=work/'新 调研底稿.xlsx';b=work/'新 彩虹底稿.xlsx'
    shutil.copy2(p['report_output'],a);shutil.copy2(p['rainbow_output'],b)
    cfg=save_configuration('selected',a,b,path=work/'test-selection.json')
    selected=Path(prepare_selected_inputs(work,cfg));chosen=load(selected/'table-validation-plan.json')
    for kind in ['report','rainbow']:assert sha(chosen[kind+'_output'])==hashes[kind]
    inspection=work/'inspection.json';inspect(chosen['report_output'],chosen['rainbow_output'],inspection)
    sgd=plan_multi(seed['sgd_source'],chosen['report_output'],chosen['rainbow_output'],inspection,work/'sgd-plan',approved=baseline(ROOT))
    bp=board_plan(seed['board_source'],work/'board-plan',chosen)
    assert len(bp['details'])==2734
    assert len(bp['matrices'])==7 and {x['currency'] for x in bp['histories']}=={'USD','CNY'}
    m=next(x for x in bp['matrices'] if x['currency']=='SGD')
    sf=next(g for g in m['groups'] if g['bank']=='Singapura Finance');assert len(sf['rows'])==2
    assert sha(CONFIG)==config_hash
    for kind in ['report','rainbow']:assert sha(p[kind+'_output'])==hashes[kind]
    result=dict(passed=True,settings_unchanged=True,originals_unchanged=True,board_quotes=len(bp['details']),report_matrices=len(bp['matrices']),sgd_plan=str(work/'sgd-plan/table-validation-plan.json'),snapshot=str(selected))
    save(work/'checks.json',result);print('Selected workbook snapshot and SGD/board insertion plans passed: '+str(work))

if __name__=='__main__':check()

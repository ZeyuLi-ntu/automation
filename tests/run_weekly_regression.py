"""Native Excel integration with explicitly synthetic future periods, no live approval."""
import argparse
from copy import deepcopy
from datetime import date,timedelta
import os
from pathlib import Path
import subprocess
import sys
from market_rates.common import load,save
from market_rates.table_validation import sha
from market_rates.multi_bank_validation import plan_multi
from market_rates.weekly_history import identity

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline-output',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    root=Path(a.out).resolve();root.mkdir(parents=True,exist_ok=False)
    original=load(Path(a.baseline_output)/'table-validation-plan.json');source=Path(original['source_run'])
    runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
    py=runtime/'python/python.exe';node=runtime/'node/bin/node.exe'
    env=dict(os.environ,MARKET_NODE_MODULES=str(runtime/'node/node_modules'),PYTHONUTF8='1')
    env={k:v for k,v in env.items() if k.casefold()!='psmodulepath'}
    approved=dict(id='SYNTHETIC-TEST-BASELINE',groups=deepcopy(original['groups']),bank_dates=original['bank_dates'],overrides={},manual_notes={})
    report=original['report_output'];rainbow=original['rainbow_output']
    run0=load(source/'run.json');cfg=load(source/'config.snapshot.json');results=[]
    def command(args):subprocess.run([str(v) for v in args],cwd=ROOT,env=env,check=True)
    for week,rate in [(1,'1.91'),(2,'2.03')]:
        folder=root/f'week-{week}';folder.mkdir();run=deepcopy(run0)
        run['as_of']=(date.fromisoformat(original['as_of'])+timedelta(days=7*week)).isoformat()
        run['id']='SYNTHETIC-WEEK-'+str(week);run['collection_label']='SYNTHETIC-ROLLING-TEST';run['demo']=True
        run['bank_dates']={b:run['as_of'] for b in cfg['expected_banks']}
        for lane in ['llm','vlm']:
            for r in run[lane]['offers']:
                r['valid_from']=None;r['valid_to']=None
                if r['product_id']=='cimb-sgd-online' and r['tenor_value']==6 and r['audience']=='personal':r['rate_pct']=rate
        save(folder/'run.json',run);save(folder/'config.snapshot.json',cfg);save(folder/'result.json',dict(pending=1,reason='SYNTHETIC TEST ONLY'))
        save(folder/'benchmark.json',dict(kind='synthetic_test_fixture',evidence_hash=run['evidence_hash'],run_sha256=sha(folder/'run.json'),lanes={l:dict(matched=len(run[l]['offers']),expected=len(run[l]['offers']),unexpected=[]) for l in ['llm','vlm']}))
        inspection=folder/'inspection.json';out=folder/'output'
        command([py,'-m','scripts.inspect_weekly_templates','--report',report,'--rainbow',rainbow,'--out',inspection])
        plan=plan_multi(folder,report,rainbow,inspection,out,approved=approved)
        assert plan['date_column_shift']==1
        # The new BOC product must update its existing span, never append again.
        assert not plan['report_inserts'],plan['report_inserts']
        command([node,'scripts/build_validation_inputs.mjs',out])
        command(['powershell','-NoProfile','-File','scripts/validate_three_bank_excel.ps1','-PlanPath',out/'table-validation-plan.json'])
        command([py,'-m','tests.verify_weekly_values','--plan',out/'table-validation-plan.json','--week',week])
        results.append(dict(week=week,as_of=run['as_of'],input_sheet=plan['input_sheet'],report=plan['report_output'],status='passed'))
        report=plan['report_output'];rainbow=plan['rainbow_output'];approved['groups']=plan['groups'];approved['bank_dates']=run['bank_dates']
    save(root/'weekly-regression.json',dict(synthetic=True,production_history_changed=False,periods=results))
    print('两次跨周滚动均通过；测试文件不会登记到正式历史。')

if __name__=='__main__':main()

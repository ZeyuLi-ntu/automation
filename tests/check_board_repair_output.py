"""Live-artifact regression: refreshed banks, dates and replay layout."""
from collections import Counter
from pathlib import Path
import tempfile
import argparse
from market_rates.common import load,save
from market_rates.board_wide_plan import plan

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    out=Path(args.output or load('outputs/latest-board-pilot.json')['output']);base=load(out/'table-validation-plan.json');details=base['details'];checks=[]
    def ck(name,condition):
        assert condition,name
        checks.append(name)
    for bank,cur in [('BEA','SGD'),('BEA','USD'),('HSBC','SGD'),('HSBC','USD'),('Maybank','SGD'),('SCB','GBP'),('CIMB','CNH')]:
        rows=[r for r in details if r['bank']==bank and r['currency']==cur]
        ck(bank+'/'+cur+' has verified numeric rows',any(r['insertable'] for r in rows))
    ck('No JPY active records',not any(r['currency']=='JPY' for r in details))
    ck('All future-effective rows held',all(not r['insertable'] for r in details if r.get('valid_from') and r['valid_from']>base['as_of']))
    mb=[r for r in details if r['bank']=='Maybank' and r['currency']=='SGD']
    ck('Maybank 1M minimum',all(float(r['amount_min'])>=10000 for r in mb if r['tenor_value']==1))
    ck('Maybank 36M rollover condition',all('续期' in r['conditions'] for r in mb if r['tenor_value']==36))
    ck('CIMB N/A is missing not zero',not any(r['bank']=='CIMB' and r['currency']=='CNH' and r['tenor_value']==1 and r['amount_min']=='10000' for r in details))
    ck('User percent policy includes SCB SGD with known amounts',all(r['insertable'] for r in details if r['bank']=='SCB' and r['currency']=='SGD' and r['amount_min'] is not None))
    with tempfile.TemporaryDirectory(prefix='board-repair-replay-') as temp:
        replay=plan(base['source_run'],Path(temp)/'plan',base)
        for field in ['matrices','histories','rainbow_blocks','rainbow_cells','summary','rainbow_shift']:
            ck('Replay retains exact '+field,replay[field]==base[field])
    save(out/'repair-business-checks.json',dict(passed=True,checks=checks,counts=dict(Counter(r['bank'] for r in details))))
    print('Repair business and same-run replay checks passed:',len(checks))

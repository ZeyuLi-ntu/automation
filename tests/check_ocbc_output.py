"""Checks the delivered OCBC scope and preservation independently of capture."""
from pathlib import Path
from collections import Counter
import argparse, tempfile
from market_rates.common import load, save
from market_rates.board_wide_plan import plan
from market_rates.schema import facts

def check(out):
    out=Path(out);p=load(out/'table-validation-plan.json');r=load(Path(p['source_run'])/'run.json')
    previous=load(Path(r['parents'][0])/'run.json');checks=[]
    def ck(name,ok):
        if not ok:raise AssertionError(name)
        checks.append(name)
    required={'SGD','USD','AUD','NZD','CAD','HKD','EUR','GBP'}
    ocbc=[d for d in p['details'] if d['bank']=='OCBC']
    ck('All eight Bank List currencies',set(d['currency'] for d in ocbc)==required)
    ck('Every OCBC quote insertable without human acceptance',len(ocbc)==437 and all(d['insertable'] and not d['hold_reason'] for d in ocbc))
    ck('FX matrix complete at every source tier and tenor',Counter(d['currency'] for d in ocbc)==Counter(dict.fromkeys(required-{'SGD'},45),SGD=122))
    ck('Source literal zeros are retained',all(d['rate_pct']=='0' for d in ocbc if d['currency']=='EUR'))
    ck('SGD long tenors explicitly renewal only',all('仅同期限旧存款续期' in d['conditions'] for d in ocbc if d['currency']=='SGD' and d['tenor_value']>=24))
    ck('Value Date not misused as future quote date',all(d['valid_from']<=p['as_of'] for d in ocbc if d['valid_from']))
    other=lambda run:[facts(o) for o in run['llm']['offers'] if o['bank']!='OCBC']
    ck('Other banks source facts unchanged',other(r)==other(previous))
    coverage=load(out/'board-coverage.json');cr=[c for c in coverage['rows'] if c['bank']=='OCBC']
    ck('Saved report contains numeric cells in all eight currencies',len(cr)==8 and all(c['status']=='present' and c['output_numeric_count']>0 for c in cr))
    ck('Same-day revision does not add duplicate history dates',all(not h['insert_date'] for h in p['histories']))
    offered={(d['currency'],str(d['tenor_value'])+d['tenor_unit']) for d in ocbc}
    ck('OCBC appears in every supported SGD/USD rainbow tenure',all(any(g['bank']=='OCBC' and any(isinstance(x['expected'],(float,int)) for x in g['rows']) for g in b['groups']) for b in p['rainbow_blocks'] if (b['currency'],b['tenor']) in offered))
    with tempfile.TemporaryDirectory(prefix='ocbc-replay-') as temp:
        replay=plan(p['source_run'],Path(temp)/'plan',p)
        for field in ['matrices','histories','rainbow_blocks','rainbow_cells','summary','rainbow_shift']:
            ck('Repeat generation preserves '+field,replay[field]==p[field])
    save(out/'ocbc-checks.json',dict(passed=True,checks=checks,currency_counts=dict(Counter(d['currency'] for d in ocbc))))
    print('OCBC output and replay checks passed:',len(checks))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output');x=a.parse_args();check(x.output or load('outputs/latest-board-pilot.json')['output'])

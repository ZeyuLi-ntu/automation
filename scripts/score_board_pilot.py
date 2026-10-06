"""Fixed-source qualification, separate from model agreement. No manual approval."""
from pathlib import Path
from market_rates.common import load,save
from market_rates.table_validation import sha
from market_rates.pipeline import check_evidence

def score(root):
    root=Path(root);run=load(root/'run.json');check_evidence(run,root/'evidence')
    contract=load('config/board-pilot-source-contract.json');checks=[]
    # A pinned benchmark qualifies this captured source only, not changing live rates.
    original=load(Path(contract['evidence_run'])/'run.json')
    if run['evidence_hash']!=original['evidence_hash']:raise ValueError('A new capture needs a new independently checked source contract')
    for t in contract['tables']:
        expected={(int(m),'M',r,tier['min'],tier['max'],True,False,tier['channel'],t['basis'],t['effective'],t['currency'],'all') for m,r in t['rates'].items() for tier in t['tiers']}
        for lane in ['llm','vlm']:
            rows=[r for r in run[lane]['offers'] if r['bank']==t['bank'] and r['currency']==t['currency']]
            actual={(r['tenor_value'],r['tenor_unit'],r['rate_pct'],r['amount_min'],r['amount_max'],r['min_inclusive'],r['max_inclusive'],r['channel'],r['rate_basis'],r['valid_from'],r['amount_currency'],r['audience']) for r in rows}
            checks.append(dict(bank=t['bank'],currency=t['currency'],lane=lane,expected=len(expected),actual=len(rows),passed=expected==actual and len(actual)==len(rows)))
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,evidence_hash=run['evidence_hash'],run_sha256=sha(root/'run.json'),contract_sha256=sha('config/board-pilot-source-contract.json'),human_reviewed=False)
    save(root/'benchmark.json',result)
    if not result['passed']:raise ValueError('Fixed source benchmark mismatch')
    return result
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();print(score(a.run))

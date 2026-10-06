"""Create a strictly qualified draft from frozen pilot evidence; no human approval."""
from datetime import datetime
from pathlib import Path
from market_rates.common import load,save
from market_rates.consolidate import consolidate,qualify
from market_rates.coverage_status import public_inventory,failed_collection
from market_rates.table_validation import sha

ROOT=Path(__file__).resolve().parents[1]
NEW=['remaining-BEA-20260927-v2','remaining-HSBC-20260927-v2','remaining-SingFinance-20260927-v3',
     'remaining-Singapura-Finance-20260927-v3','remaining-CITI-20260927-v6']

def main():
    pins=load(ROOT/'config/validated-batches.json')
    folders=[ROOT/s['path'] for s in pins['sources'] if not s.get('remaining_bank_batch')]
    for n in NEW:
        folder=ROOT/'runs'/n;gate=qualify(folder,allow_agreement=True)
        run=load(folder/'run.json')
        save(folder/'benchmark.json',dict(kind=gate['kind'],lanes=gate['lanes'],
           evidence_hash=run['evidence_hash'],run_sha256=sha(folder/'run.json')))
        folders.append(folder)
    coverage=public_inventory(ROOT/'runs/public-status-20260927')
    coverage.append(failed_collection('Maybank',ROOT/'runs/remaining-Maybank-20260927-v2'))
    work=ROOT/'runs'/('sgd-coverage-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    # Every supplied source must pass qualify(). Failed/absent sources contain no numeric offers.
    consolidate(folders,work/'combined','SGD全行覆盖_待复核',coverage=coverage)
    save(work/'workflow.json',dict(project=str(ROOT),mode='rebuild',completed=['合并银行'],status='running',sources=[str(f) for f in folders]))
    pins['sources']=[s for s in pins['sources'] if not s.get('remaining_bank_batch')]
    for folder in folders[-len(NEW):]:
        pins['sources'].append(dict(path=folder.relative_to(ROOT).as_posix(),remaining_bank_batch=True,
            hashes={n:sha(folder/n) for n in ['run.json','result.json','benchmark.json']}))
    pins.update(scope='15 banks with qualified quotations; 4 public no-quote statuses; Maybank local collection blocked',
      public_status_path='runs/public-status-20260927',coverage=coverage)
    save(ROOT/'config/validated-batches.json',pins)
    print(work)

if __name__=='__main__':main()

"""Pin independently extracted Maybank bundle evidence and rebuild the requested scope."""
from datetime import datetime
from pathlib import Path
from market_rates.common import load,save
from market_rates.consolidate import consolidate,qualify
from market_rates.table_validation import sha
from market_rates.workbook_policy import bank_in_scope

ROOT=Path(__file__).resolve().parents[1]

def main():
    pins=load(ROOT/'config/validated-batches.json');folder=ROOT/'runs/maybank-bundle-import-20260927'
    qualify(folder)
    pins['sources']=[s for s in pins['sources'] if not s.get('maybank_bundle_import')]
    pins['sources'].append(dict(path=folder.relative_to(ROOT).as_posix(),maybank_bundle_import=True,
        hashes={n:sha(folder/n) for n in ['run.json','result.json','benchmark.json']}))
    pins['coverage']=[c for c in pins.get('coverage',[]) if bank_in_scope(c['bank']) and c['bank']!='Maybank']
    pins['scope']='16 banks with quotations, including imported Maybank official text/user image; DBS/POSB public status; MARI/TRUST excluded'
    work=ROOT/'runs'/('maybank-bundle-scope-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    sources=[ROOT/s['path'] for s in pins['sources']]
    consolidate(sources,work/'combined','SGD促销修正版',coverage=pins['coverage'])
    save(work/'workflow.json',dict(project=str(ROOT),mode='rebuild',completed=['合并银行'],status='running',sources=[str(s) for s in sources]))
    save(ROOT/'config/validated-batches.json',pins)
    print(work)

if __name__=='__main__':main()

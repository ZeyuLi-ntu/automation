import argparse
from pathlib import Path
from market_rates.common import load,save
from market_rates.board_batch import extract
from market_rates.multi_bank_validation import raw_matched_offers
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();root=Path(a.run)
    cfg=load('config/project.local.json');r=extract(root,cfg);offers,blocked=raw_matched_offers(r)
    save(root/'agreement.json',dict(accepted=len(offers),blocked=blocked,human_reviewed=False))
    if blocked:raise ValueError(str(blocked))
    from scripts.check_board_currency import check
    check(root)
    print('Agreed:',len(offers),flush=True)

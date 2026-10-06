import argparse
from pathlib import Path
from market_rates.common import load,save
from market_rates.board_extractor import extract
from market_rates.multi_bank_validation import raw_matched_offers

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();root=Path(a.run)
    cfg=load('config/project.local.json');cfg.update(rate_scopes=[dict(currency=c,rate_type='board') for c in ['SGD','USD']],allow_actual_tenors=True)
    run=extract(load(root/'run.json'),root,cfg);offers,blocked=raw_matched_offers(run)
    save(root/'config.snapshot.json',cfg)
    save(root/'agreement.json',dict(kind='dom_and_dual_agreement',accepted=len(offers),blocked=blocked,human_reviewed=False))
    if blocked:raise ValueError('Review required: '+str(blocked))
    print({'agreed_offers':len(offers),'core_disagreements':blocked},flush=True)

if __name__=='__main__':main()

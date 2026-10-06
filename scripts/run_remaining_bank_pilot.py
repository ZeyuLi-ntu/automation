"""One-bank resumable extraction; keeps network failures isolated by institution."""
import argparse
from market_rates.remaining_banks import BANKS,configuration as config
from market_rates.common import save
from pathlib import Path

if __name__=='__main__':
    import scripts.run_next_bank_pilot as runner
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--bank',required=True,choices=list(BANKS));a,_=p.parse_known_args()
    def configuration(links,out):
        Path(out).mkdir(parents=True);c=config(a.bank,links=links);save(Path(out)/'sources.json',c['sources']);return c
    runner.BANKS=BANKS;runner.configuration=configuration;runner.main()

"""FX entry point for shared local screenshot/text repair."""
import argparse
from pathlib import Path
from market_rates.common import load
from scripts.verify_with_repair import check

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--config',default='config/project.local.json');a=p.parse_args();check(a.run,load(a.config))

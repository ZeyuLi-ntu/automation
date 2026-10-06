"""Explicit human action, separate from collection and draft generation."""
import argparse
from pathlib import Path
from market_rates.common import load
from market_rates.weekly_history import approve

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--acknowledgement',required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    out=a.output or load(root/'outputs/latest-workflow.json')['output']
    record=approve(root,out,a.acknowledgement)
    print('已登记人工确认版本：'+record['as_of']+'；下次从此版本继续滚动。\n'+record['report'])

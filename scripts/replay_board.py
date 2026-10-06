"""Dispatch the latest saved board dataset without fetching or model calls."""
from pathlib import Path
import subprocess,sys
from market_rates.common import load
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    ptr=load(ROOT/'outputs/latest-board-pilot.json');p=load(Path(ptr['output'])/'table-validation-plan.json')
    module={'board-wide':'scripts.run_board_wide','board-batch':'scripts.run_board_batch'}.get(p.get('kind'),'scripts.run_board_workflow')
    raise SystemExit(subprocess.call([sys.executable,'-X','utf8','-m',module],cwd=ROOT))

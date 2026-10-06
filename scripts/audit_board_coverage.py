"""Audit every required Bank List board cell against current data and saved files."""
import argparse
from pathlib import Path
from market_rates.common import load
from market_rates.board_coverage import ROOT,write_audit


def main():
    a=argparse.ArgumentParser();a.add_argument('--output');a.add_argument('--scope-workbook')
    a.add_argument('--investigations');a.add_argument('--require-complete',action='store_true');args=a.parse_args()
    out=Path(args.output or load(ROOT/'outputs/latest-board-pilot.json')['output'])
    notes_path=Path(args.investigations) if args.investigations else out/'board-coverage-investigations.json'
    notes=load(notes_path) if notes_path.exists() else None
    result=write_audit(load(out/'table-validation-plan.json'),out,workbook=args.scope_workbook,investigations=notes)
    print({k:result[k] for k in ['required_count','bank_count','counts','pairs_with_numeric_output','missing_or_fully_held','saved_output_inspected']})
    if args.require_complete and not result['required_pair_availability_complete']:
        raise SystemExit('挂牌覆盖不完整；不得按全量完成发布。请查看 board-coverage.html')


if __name__=='__main__':main()

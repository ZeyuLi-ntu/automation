"""Repeat only rate requests locally; retain unchanged terms-response caches."""
import argparse,runpy,sys
from market_rates import multi_bank_extractor

def main():
    a=argparse.ArgumentParser();a.add_argument('--run',required=True);a.add_argument('--bank',choices=['CIMB','HLF'],required=True);a.add_argument('--lane',choices=['llm','vlm'],required=True);args=a.parse_args()
    # Clarify table associations without supplying any rates or deposit bounds.
    multi_bank_extractor.INSTRUCTIONS+='\nTABLE ALIGNMENT CHECK: Read one physical data row at a time. For that row keep the printed tenor attached to every customer-column rate; do not move any rate into another tenor. Re-read the row label before emitting each record. If a deposit tier is a printed range, every rate in that tier inherits BOTH its lower and upper bounds and the printed inclusivity. A ceiling printed in a tier label is explicit, even when it is shared across several rate columns. Do not replace a printed ceiling with null. Use only this request source; no earlier answer is provided.'
    sys.argv=['scripts.run_three_bank_pilot','--out',args.run,'--resume','--bank',args.bank,'--lane',args.lane,'--reprocess']
    runpy.run_module('scripts.run_three_bank_pilot',run_name='__main__')

if __name__=='__main__':main()

import argparse
from market_rates.table_validation import make_validation_plan

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',required=True)
    parser.add_argument('--report',required=True)
    parser.add_argument('--rainbow',required=True)
    parser.add_argument('--out',required=True)
    a=parser.parse_args()
    p=make_validation_plan(a.run,a.report,a.rainbow,a.out)
    print('副本验证计划已生成；原复核状态保留:',p['source_pending'])

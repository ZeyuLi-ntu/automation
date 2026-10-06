import argparse
from pathlib import Path
from market_rates.common import save
from market_rates.multi_bank_validation import plan_multi
p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out',required=True);p.add_argument('--revision',action='store_true');a=p.parse_args()
r=plan_multi(a.run,'../20260916市场利率调研.xlsx','../彩虹表_按MarketRateData更新_20260916_17.59.xlsx',
             'runs/three-bank-20260925/template-inspection.json',a.out)
if a.revision:
    for kind in ['report','rainbow']:r[kind+'_output']=r[kind+'_output'].replace('副本.xlsx','修正版.xlsx')
    save(Path(a.out)/'table-validation-plan.json',r)
print({'offers':len(r['details']),'groups':len(r['groups']),'new_rows':sum(i['count'] for i in r['report_inserts'])})

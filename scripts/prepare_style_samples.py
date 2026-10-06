"""Group every raw-style difference for comparison through Excel's own renderer."""
from collections import Counter
from pathlib import Path
import openpyxl
from market_rates.common import load, save

out=Path('outputs/01a0d32d-scb-table-validation')
plan=load(out/'table-validation-plan.json'); report=load(out/'table-validation-checks.json')
samples=[]
for kind in ['report','rainbow']:
    a=openpyxl.load_workbook(plan[kind+'_template']);b=openpyxl.load_workbook(plan[kind+'_output'])
    groups={}
    for k,sn,source,target in report['style_differences']:
        if k!=kind: continue
        key=(sn,a[sn][source].style_id,b[sn][target].style_id,type(a[sn][source]).__name__,type(b[sn][target]).__name__)
        if key not in groups: groups[key]={'kind':kind,'sheet':sn,'source':source,'target':target,'represented_cells':0}
        groups[key]['represented_cells']+=1
    samples.extend(groups.values())
save(out/'style-samples.json',samples)
print('Unique style pairs:',len(samples),'represented cells:',sum(s['represented_cells'] for s in samples))

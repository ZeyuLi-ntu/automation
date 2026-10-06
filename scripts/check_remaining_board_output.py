"""Read the delivered workbooks, checking newly completed currencies and source facts."""
import argparse
from pathlib import Path
from decimal import Decimal
import openpyxl
from market_rates.common import load,save

def check(out):
    out=Path(out);p=load(out/'table-validation-plan.json');coverage=load(out/'board-coverage.json');checks=[]
    def ck(name,condition):
        if not condition:raise AssertionError(name)
        checks.append(name)
    ck('99 required bank/currency pairs have saved current numbers',coverage['saved_output_inspected'] and coverage['required_count']==99 and coverage['pairs_with_numeric_output']==99 and coverage['missing_or_fully_held']==0)
    required={'DBS':'USD AUD NZD CAD HKD EUR GBP','CIMB':'SGD','HLB':'HKD','RHB':'USD CNY AUD NZD CAD HKD EUR GBP','SBI':'AUD GBP','UOB':'USD CNY AUD NZD CAD HKD GBP'}
    for bank,currencies in required.items():
        for currency in currencies.split():
            rows=[r for r in coverage['rows'] if r['bank']==bank and r['currency']==currency]
            ck(bank+'/'+currency+' numeric output',len(rows)==1 and rows[0]['output_numeric_count']>0)
    facts=[('UOB','CNH',3,'250000','1'),('RHB','CNY',3,None,'0.45'),('DBS','USD',3,None,'3.78'),('SBI','GBP',3,'10000','0.05'),('SBI','AUD',3,'10000','0.1'),('HLB','HKD',1,None,'1.9035'),('CIMB','SGD',3,'1000','0.3')]
    ds=p['details'];selected=[]
    for bank,cur,tenor,minimum,rate in facts:
        rows=[d for d in ds if d['bank']==bank and d['currency']==cur and d['tenor_unit']=='M' and d['tenor_value']==tenor and d['amount_min']==minimum and Decimal(d['rate_pct'])==Decimal(rate)]
        ck(bank+cur+' source example',len(rows)==1 and rows[0]['insertable']);selected+=rows
    ck('Old published SBI dates remain eligible',all(d['source_date']=='2024-10-01' and d['insertable'] for d in ds if d['bank']=='SBI' and d['currency'] in ['AUD','GBP']))
    ck('Unknown HLB HKD minimum was not invented',all(d['amount_min'] is None and d['insertable'] for d in ds if d['bank']=='HLB' and d['currency']=='HKD'))
    ck('No excluded banks or yen',not any(d['bank'] in ['Trust','TRUST','MariBank'] or d['currency']=='JPY' for d in ds))
    ck('Same-day rebuild has no duplicate date columns',all(not h['insert_date'] for h in p['histories']))
    for kind in ['report','rainbow']:
        book=openpyxl.load_workbook(p[kind+'_output'],data_only=True);sheet=book[p['input_sheet']]
        for d in selected:
            value=sheet.cell(d['input_row'],9).value
            ck(kind+' saved '+d['bank']+d['currency'],isinstance(value,(int,float)) and abs(Decimal(str(value))-Decimal(d['rate_pct'])/100)<Decimal('0.000000001'))
        if kind=='report':
            for row in coverage['rows']:
                for c in row['output_cells']:
                    v=book[c['sheet']][c['cell']].value
                    ck('saved coverage '+c['sheet']+c['cell'],isinstance(v,(int,float)) and abs(Decimal(str(v))-Decimal(c['value']))<Decimal('0.000000001'))
        book.close()
    save(out/'remaining-board-checks.json',dict(passed=True,checks=len(checks),results=checks))
    print('Remaining board saved-file checks:',len(checks),'passed')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);check(a.parse_args().output)

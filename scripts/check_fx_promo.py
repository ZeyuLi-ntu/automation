"""Saved-value reconciliation and preservation of all previously completed work."""
import argparse,re,math,hashlib
from pathlib import Path
from market_rates.common import load,save
from market_rates.xlsx_read import read_xlsx,merged_ranges
from market_rates.board_plan import cell_number,col
from market_rates.rules import main_offer

def check(out):
    out=Path(out);p=load(out/'table-validation-plan.json');checks=[]
    def equal(a,b):
        a,b=cell_number(a),cell_number(b)
        return abs(a-b)<1e-10 if isinstance(a,(int,float)) and isinstance(b,(int,float)) else a==b or a in [None,''] and b in [None,'']
    def test(name,a,b):
        ok=equal(a,b);checks.append(dict(check=name,passed=ok))
        if not ok:raise AssertionError(f'{name}: {a!r} != {b!r}')
    before={k:read_xlsx(p[k+'_template'],merge_anchors_only=True) for k in ['report','rainbow']};after={k:read_xlsx(p[k+'_output'],merge_anchors_only=True) for k in ['report','rainbow']}
    from market_rates.sgd_comparison import check_saved as check_sgd
    sgd_deltas={x['address']:x['expected'] for x in check_sgd(p['report_output'],after['report'])}
    for kind in ['report','rainbow']:
        test(kind+' original SHA',hashlib.sha256(Path(p[kind+'_template']).read_bytes()).hexdigest(),p[kind+'_sha256'])
        exempt={'USD促销','CNY促销','其他外币促销利率','最高报价汇总 '} if kind=='report' else {'USD Rate + Other Currency Rates'}
        for name,s in before[kind].items():
            if name in exempt:continue
            for addr,v in s.items():
                if kind=='report' and name=='Bank List' and addr in {c['address'] for c in p.get('coverage',[])}:continue
                if kind=='report' and name=='SGD促销' and addr in sgd_deltas:
                    test(kind+'/'+name+'/'+addr,after[kind][name].get(addr),sgd_deltas[addr]);continue
                test(kind+'/'+name+'/'+addr,after[kind][name].get(addr),v)
    for c in p.get('coverage',[]):test('Coverage/'+c['address'],after['report']['Bank List'].get(c['address']),c['expected'])
    for h in p['histories']:
        s=after['report'][h['sheet']];old=before['report'][h['sheet']];cc=h['current_col'];shift=lambda row:row+sum(i['count'] for i in h['inserts'] if i['before']<=row)
        for c in h['existing']:test(h['sheet']+'/'+c['address'],s.get(c['address']),c['expected'])
        for i in h['inserts']:
            skip=2 if i.get('kind')=='tenor' else 0
            for n,r in enumerate(i['rows']):test(h['sheet']+'/'+str(i['target_row']+n+skip),s.get(col(cc)+str(i['target_row']+n+skip)),r['expected'])
        delta_cols={re.match(r'[A-Z]+',a)[0] for a,x in old.items() if x in ['当日增幅','当日最高报价变动']}
        for addr,v in old.items():
            if v is None:continue
            letters,num=re.fullmatch(r'([A-Z]+)(\d+)',addr).groups();c=0
            for letter in letters:c=c*26+ord(letter)-64
            # Prior dated columns must retain every old observation exactly.
            if c<cc+(0 if h['insert_date'] else 1) or letters in delta_cols:continue
            test('History '+h['sheet']+'/'+addr,s.get(col(c+(1 if h['insert_date'] else 0))+str(shift(int(num)))) ,v)
    s=after['report']['最高报价汇总 ']
    for c in p['summary']:test('Summary/'+c['address'],s.get(c['address']),c['expected'])
    for addr,v in before['report']['最高报价汇总 '].items():
        if addr in {c['address'] for c in p['summary']} or addr in ['B27','E27']:continue
        test('Summary preserved/'+addr,s.get(addr),v)
    s=after['rainbow']['USD Rate + Other Currency Rates'];off=p['usd_delta']+p['cny_delta']
    for addr,v in before['rainbow']['USD Rate + Other Currency Rates'].items():
        letters,num=re.fullmatch(r'([A-Z]+)(\d+)',addr).groups();num=int(num)
        if 31<=num<=103:test('Rainbow board preserved/'+addr,s.get(letters+str(num+off)),v)
    for bl in p['rainbow_blocks']:
        ranks=[g['rank'] for g in bl['groups']];test('Rank descending '+bl['currency']+bl['tenor'],ranks,sorted(ranks,reverse=True))
        for g in bl['groups']:
            for i,r in enumerate(g['rows']):test('Rainbow '+bl['currency']+str(g['target_row']+i),s.get(col(bl['col']+1)+str(g['target_row']+i)),r['expected'])
    for c in p['mixed_cells']:test('Mixed/'+c['address'],s.get(c['address']),c['expected'])
    for kind in ['report','rainbow']:
        si=after[kind][p['input_sheet']]
        for r in p['details']:test('Inputs '+kind+str(r['input_row']),si.get('I'+str(r['input_row'])),float(r['rate_pct'])/100 if r['insertable'] else '-')
        errs=[(n,a,v) for n,sheet in after[kind].items() for a,v in sheet.items() if isinstance(v,str) and v.startswith(('#REF!','#VALUE!','#DIV/0!','#NAME?','#NUM!'))]
        prior=[(n,a,v) for n,sheet in before[kind].items() for a,v in sheet.items() if isinstance(v,str) and v.startswith(('#REF!','#VALUE!','#DIV/0!','#NAME?','#NUM!'))]
        test('No new formula errors '+kind,len(errs),len(prior))
    test('Every insertable quote in research',sum(len(i['rows']) for h in p['histories'] for i in h['inserts'])+sum(bool(e.get('input_row')) for h in p['histories'] for e in h['existing']),sum(r['insertable'] for r in p['details']))
    test('Every eligible quote in existing rainbow tenors',sum(len(g['rows']) for bl in p['rainbow_blocks'] for g in bl['groups']),sum(r.get('rainbow_insertable',r['insertable']) for r in p['details']))
    test('Excluded banks and JPY',any(r['bank'] in ['MariBank','Trust'] or r['currency']=='JPY' for r in p['details']),False)
    test('Expired quotes explicitly labeled as references',all(r.get('reference_quote') for r in p['details'] if r['insertable'] and r.get('valid_to') and r['valid_to']<p['as_of']),True)
    from scripts.check_board_cleanup import check_deltas
    deltas=check_deltas(p['report_output'],after['report'])
    result=dict(passed=True,checks=checks,count=len(checks),details=len(p['details']),insertable=sum(r['insertable'] for r in p['details']),unchanged_board=True,delta_rows=deltas);save(out/'fx-checks.json',result);print('FX checks passed',len(checks));return result
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);check(a.parse_args().out)

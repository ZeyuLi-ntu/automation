"""Read-only independent round-trip and preservation checks; never resaves xlsx."""
from pathlib import Path
from math import isclose
import argparse,hashlib,json,html
import openpyxl

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def check_output(out):
    out=Path(out);p=read(out/'table-validation-plan.json');checks=[]
    def check(name,condition):checks.append(dict(name=name,passed=bool(condition)))
    def eq(a,b):return isclose(a,b,rel_tol=0,abs_tol=1e-11) if isinstance(a,(int,float)) and isinstance(b,(int,float)) else a==b
    for kind in ['report','rainbow']:
        src=openpyxl.load_workbook(p[kind+'_template'],data_only=False);w=openpyxl.load_workbook(p[kind+'_output'],data_only=False)
        values=openpyxl.load_workbook(p[kind+'_output'],data_only=True);oldvalues=openpyxl.load_workbook(p[kind+'_template'],data_only=True)
        changed={'SGD挂牌','USD挂牌','最高报价汇总 '} if kind=='report' else {'SGD Board Rate','USD Rate + Other Currency Rates'}
        for name in src.sheetnames:
            if name in changed:continue
            a={c.coordinate:c.value for row in src[name] for c in row if c.value is not None};b={c.coordinate:c.value for row in w[name] for c in row if c.value is not None}
            check(kind+' untouched '+name,a==b)
        check(kind+' input sheet present',p['input_sheet'] in w.sheetnames)
        new_errors=[]
        for sheet in values:
            for row in sheet:
                for cell in row:
                    if cell.data_type!='e':continue
                    r,c=cell.row,cell.column
                    if kind=='report' and sheet.title=='USD挂牌' and c>=5:c-=1
                    if kind=='report' and sheet.title=='SGD挂牌' and r>=50:r-=1
                    old=oldvalues[sheet.title].cell(r,c) if sheet.title in oldvalues.sheetnames else None
                    if old is None or old.data_type!='e':new_errors.append(sheet.title+'!'+cell.coordinate+' '+str(cell.value))
        check(kind+' no new Excel errors',not new_errors)
        if new_errors:checks[-1]['detail']=new_errors
        for d in p['details']:
            expect=float(d['rate_pct'])/100 if d['insertable'] else '-'
            check(kind+' input I'+str(d['input_row']),eq(values[p['input_sheet']].cell(d['input_row'],9).value,expect))
        if kind=='report':
            for m in p['matrix']:
                for c in m['cells']:check('matrix '+c['address'],eq(values['SGD挂牌'][c['address']].value,c['expected']))
            check('HLB one merged bank block','A48:A49' in str(w['SGD挂牌'].merged_cells))
            for m in p['usd_rows']:check('USD current D'+str(m['row']),eq(values['USD挂牌'].cell(m['row'],4).value,m['expected']))
            prior=True
            for row in oldvalues['USD挂牌'].iter_rows(min_col=4,max_col=249):
                for c in row:
                    # Wide merged section titles are anchored in B, not in dates.
                    if not eq(c.value,values['USD挂牌'].cell(c.row,c.column+1).value):prior=False;break
            check('all USD historical date values preserved',prior)
            check('USD merged section titles preserved',all(f'B{r-1}:IR{r-1}' in str(w['USD挂牌'].merged_cells) for r in p['usd_date_rows']))
            check('USD current dates all match',all(values['USD挂牌'].cell(r,4).value.strftime('%Y-%m-%d')==p['as_of'] for r in p['usd_date_rows']))
            check('USD summary uses newest D',all(w['最高报价汇总 '][a].value=='=USD挂牌!D'+str(r) for a,r in [('D52',71),('E52',118),('F52',165),('H52',228),('D50',72)]))
            icon_ranges=[]
            for cf,rules in w['USD挂牌'].conditional_formatting._cf_rules.items():
                if any(r.type=='iconSet' for r in rules):
                    icon_ranges.extend(str(cf.sqref) for area in cf.sqref.ranges if area.min_col<=4<=area.max_col)
            check('no arrow icons in USD quotes',not icon_ranges)
            for m in p['usd_rows']:
                r=m['row'];v=w['USD挂牌'].cell(r,251).value
                if isinstance(v,str) and v.startswith('='):check('delta latest two dates '+str(r),'D'+str(r)+'-E'+str(r) in v)
        else:
            for b in p['rainbow_blocks']:
                ranks=[g['rank'] for g in b['groups']];check('sorted '+b['currency']+' '+b['tenor'],ranks==sorted(ranks,reverse=True))
                for i,g in enumerate(b['groups']):
                    if i and g['rank']==b['groups'][i-1]['rank']:check('stable tie '+b['currency']+b['tenor']+g['bank'],g['order']>b['groups'][i-1]['order'])
                    r=g['target_row']
                    check('bank '+b['currency']+b['tenor']+g['bank'],values[b['sheet']].cell(r,b['col']).value==g['label'])
                    for v in g['rows']:
                        check('rainbow '+b['sheet']+f' {r}/{b["col"]}',eq(values[b['sheet']].cell(r,b['col']+1).value,v['expected']));r+=1
            # USD promotional/RMB/other-currency sections must remain intact.
            name='USD Rate + Other Currency Rates'
            unchanged=True
            for row in src[name]:
                for c in row:
                    if c.row<31 or c.row>64:
                        if c.value!=w[name][c.coordinate].value:unchanged=False
            check('USD rainbow non-board sections unchanged',unchanged)
        check(kind+' template file unchanged',hashlib.sha256(Path(p[kind+'_template']).read_bytes()).hexdigest()==p[kind+'_sha256'])
    report=dict(passed=all(x['passed'] for x in checks),checks=len(checks),failed=[x for x in checks if not x['passed']],results=checks,human_reviewed=False)
    (out/'roundtrip-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['<!doctype html><meta charset="utf-8"><title>挂牌试点验证</title><style>body{font:16px Microsoft YaHei;margin:36px;line-height:1.8;max-width:1200px}table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:9px}.note{background:#fff2cc;padding:18px}</style><h1>HLB / SBI · SGD / USD 挂牌试点</h1>',f'<p>{p["as_of"]} · 自动回读检查 {sum(x["passed"] for x in checks)}/{len(checks)} · 待人工核实</p>','<div class="note">'+'<br>'.join(map(html.escape,p['limitations']))+'</div>']
    for k,label in [('report','打开调研副本'),('rainbow','打开彩虹表副本')]:lines.append('<p><a href="'+html.escape(Path(p[k+'_output']).name)+'">'+label+'</a></p>')
    lines.append('<p><a href="http://127.0.0.1:8766">打开挂牌人工复核入口（先启动本地入口）</a></p><table><tr><th>银行/币种</th><th>实际期限</th><th>原始数值</th><th>金额/渠道</th><th>状态</th></tr>')
    for r in p['details']:
        vals=[r['bank']+'/'+r['currency'],str(r['tenor_value'])+r['tenor_unit'],r['rate_pct']+(' % p.a.' if r['rate_basis']=='annual_nominal' else ' 单位待核'),str(r['amount_min'])+' 至 '+('<' if not r['max_inclusive'] else '≤')+str(r['amount_max'])+' '+r['amount_currency']+' / '+r['channel'],'可插入验证副本，待人工复核' if r['insertable'] else '只保留明细']
        lines.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in vals)+'</tr>')
    lines.append('</table>');(out/'table-validation.html').write_text(''.join(lines),encoding='utf8')
    print({k:v for k,v in report.items() if k!='results'})
    if not report['passed']:raise ValueError('Round-trip check failed')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();check_output(a.output)

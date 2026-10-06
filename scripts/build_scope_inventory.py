"""Deterministic coverage inventory from the user's links and workbook layout."""
from pathlib import Path
import re,html
from market_rates.common import save,load
from market_rates.link_registry import entries
from market_rates.xlsx_read import read_xlsx
from market_rates.scope import bank_name
from market_rates.workbook_policy import bank_in_scope,presentation_currency
from market_rates.board_coverage import audit

ROOT=Path(__file__).resolve().parents[1]

def main():
    links=entries(ROOT.parent/'利率链接.xlsx');book=read_xlsx(ROOT.parent/'20260916市场利率调研.xlsx',merge_anchors_only=True)
    pointer=ROOT/'outputs/latest-board-pilot.json'
    latest=load(Path(load(pointer)['output'])/'table-validation-plan.json') if pointer.exists() else {}
    known={r['bank'] for r in links}|{'DBS/POSB','TRUST','MARI'};targets=[]
    for sheet,cells in book.items():
        if sheet in ['Bank List','最高报价汇总 ']:continue
        currency=re.match(r'^(SGD|USD|CNY|AUD|NZD|CAD|HKD|EUR|GBP)',sheet)
        currency=currency[1] if currency else '待按区域确认'
        typ='promo' if '促销' in sheet else 'board' if '挂牌' in sheet else '待分类'
        if typ=='board':continue # Required board coverage is Bank List, not sheet labels.
        grouped={}
        for addr,value in cells.items():
            if not isinstance(value,str) or not re.fullmatch(r'[ABC]\d+',addr):continue
            bank=bank_name(value)
            if bank in known:grouped.setdefault(bank,[]).append(addr)
        for bank,locations in grouped.items():
            candidates=[r for r in links if (r['bank']==bank or bank=='DBS/POSB' and r['bank'] in ['DBS','POSB']) and r['rate_type']==typ and
                (r['currency_hint']==currency or r['currency_hint']=='others' and currency!='SGD')]
            excluded=not bank_in_scope(bank)
            state='排除' if excluded else '待按区域确认' if typ=='待分类' or currency=='待按区域确认' else '待接入'
            if currency=='SGD' and typ=='promo' and not excluded:state='已有流程，来源新鲜度与条款仍须核验'
            targets.append(dict(bank=bank,currency=currency,rate_type=typ,sheet=sheet,locations=locations,
                layout='history' if sheet in ['USD挂牌','CNY挂牌','SGD促销','USD促销','CNY促销'] else 'matrix_or_section',
                sources=[{k:r[k] for k in ['cell','url','status']} for r in candidates],status=state,
                product_mapping='待按产品/客群/金额确认' if not excluded else '不接入'))
    coverage=audit(latest) if latest else None
    if coverage:
        for r in coverage['rows']:
            candidates=[s for s in links if s['bank'] in ([r['bank'],'POSB'] if r['bank']=='DBS' else [r['bank']]) and s['rate_type']=='board' and (s['currency_hint']==r['currency'] or s['currency_hint']=='others' and r['currency']!='SGD')]
            targets.append(dict(bank=r['bank_label'],currency=r['currency'],rate_type='board',sheet=r['sheet'],locations=['Bank List!'+r['cell']],
                layout='history' if r['currency'] in ['USD','CNY'] else 'matrix',sources=[{k:s[k] for k in ['cell','url','status']} for s in candidates],
                status=r['status_label']+f"；可插表 {r['insertable_count']} / 明细 {r['detail_count']}；当前数值 {r['output_numeric_count']} 格",product_mapping='存在数据不等于所有档位完整'))
    data=dict(version=2,source_workbook=str(ROOT.parent/'20260916市场利率调研.xlsx'),sources=links,targets=targets,
        board_coverage={k:coverage[k] for k in ['required_count','pairs_with_numeric_output','missing_or_fully_held']} if coverage else None,
        dependent_sheets=['最高报价汇总 ','Premier Rates'],rainbow_sheets=list(read_xlsx(ROOT.parent/'彩虹表_按MarketRateData更新_20260916_17.59.xlsx')),
        policy=load(ROOT/'config/workbook-policy.json'),note='来源登记与模板覆盖清单，不代表实时采集或人工已确认')
    save(ROOT/'config/scope-inventory.json',data)
    out=ROOT/'outputs/scope-inventory';out.mkdir(exist_ok=True)
    body=['<!doctype html><meta charset="utf-8"><title>覆盖范围清单</title><style>body{font:15px Microsoft YaHei;margin:32px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:7px}th{background:#e9f1f4}</style><h1>覆盖范围与挂牌批量进度</h1><p>'+html.escape(data['note'])+'</p>']
    if coverage:body.append('<p>挂牌依据 Bank List 日期格：应有 '+str(coverage['required_count'])+' 组，有本期数值 '+str(coverage['pairs_with_numeric_output'])+' 组，缺 '+str(coverage['missing_or_fully_held'])+' 组。<a href="'+(Path(load(pointer)['output'])/'board-coverage.html').as_uri()+'">完整挂牌检查</a></p>')
    body.append('<table><tr><th>银行</th><th>币种/类别</th><th>表页/布局</th><th>来源</th><th>状态</th></tr>')
    for t in targets:body.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [t['bank'],t['currency']+'/'+t['rate_type'],t['sheet']+'/'+t['layout'],', '.join(s['cell']+(' 链接缺失' if not s['url'] else '') for s in t['sources']) or '待补来源',t['status']])+'</tr>')
    body.append('</table>');(out/'index.html').write_text(''.join(body),encoding='utf8')
    print({'targets':len(targets),'source_records':len(links),'missing_links':[r['cell'] for r in links if not r['url']]})

if __name__=='__main__':main()

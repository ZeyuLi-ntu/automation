"""Independently inspect saved Excel copies and verify the source files are unchanged."""
import argparse
from copy import copy
import html
import json
from pathlib import Path
import re
import openpyxl
from openpyxl.formula import Tokenizer
from openpyxl.utils import column_index_from_string, get_column_letter
from market_rates.common import load, save
from market_rates.table_validation import sha
from market_rates.export import make_plan


def shifted_address(address):
    col,row=openpyxl.utils.cell.coordinate_from_string(address)
    number=column_index_from_string(col)
    return get_column_letter(number+(number>=3))+str(row)


def shifted_formula(formula, same_sheet=False):
    tokens=Tokenizer(formula).items
    for token in tokens:
        if token.type != 'OPERAND' or token.subtype != 'RANGE': continue
        value=token.value
        if '!' in value:
            prefix, ref=value.rsplit('!',1)
            applies=prefix.strip("'") == 'SGD促销'
        else:
            prefix,ref=None,value; applies=same_sheet
        if not applies: continue
        def shift(m):
            n=column_index_from_string(m[2]); return m[1]+get_column_letter(n+(n>=3))+m[3]
        ref=re.sub(r'(\$?)([A-Z]{1,3})(\$?\d+)',shift,ref)
        token.value=(prefix+'!' if prefix is not None else '')+ref
    return '='+''.join(t.value for t in tokens)


STYLE_CACHE = {}


def style(cell):
    identity=(cell.parent.parent,tuple(cell._style or ()))
    if identity not in STYLE_CACHE:
        STYLE_CACHE[identity]=tuple(copy(getattr(cell,k)) for k in ['font','fill','border','alignment','protection'])+(cell.number_format,)
    return STYLE_CACHE[identity]


def check(plan_path):
    plan=load(plan_path); out=Path(plan_path).resolve().parent
    checks=load(out/'native-checks.json')
    def add(name,ok,detail=''):
        checks.append({'name':name,'passed':bool(ok),'detail':detail})
    diffs=[]; style_diffs=[]; errors=[]; original_errors=[]
    allowed={'report':{'SGD促销':{'A1','B51','B52','B53'},'最高报价汇总 ':{'B2','E10'}},
             'rainbow':{'SGD Promotional Rate':{'A1','H18','H19','H20','I18','I19','I20'}}}
    books={}
    for kind in ['report','rainbow']:
        original=openpyxl.load_workbook(plan[kind+'_template'],data_only=False)
        final=openpyxl.load_workbook(plan[kind+'_output'],data_only=False)
        cached=openpyxl.load_workbook(plan[kind+'_output'],data_only=True)
        oldcache=openpyxl.load_workbook(plan[kind+'_template'],data_only=True)
        books[kind]=(final,cached)
        add(kind+'原表哈希未变化',sha(plan[kind+'_template'])==plan[kind+'_sha256'])
        add(kind+'工作表顺序及名称保留',final.sheetnames==original.sheetnames+[plan['input_sheet']])
        for ws in original:
            destination=final[ws.title]
            shifted=kind=='report' and ws.title=='SGD促销'
            for row in ws:
                for cell in row:
                    if cell.coordinate in allowed[kind].get(ws.title,set()): continue
                    column=cell.column+(1 if shifted and cell.column>=3 else 0)
                    after=destination.cell(cell.row,column)
                    expected=cell.value
                    if cell.data_type=='f' and kind=='report': expected=shifted_formula(expected,shifted)
                    if expected != after.value:
                        diffs.append([kind,ws.title,cell.coordinate,after.coordinate,str(expected),str(after.value)])
                    if style(cell)!=style(after):
                        style_diffs.append([kind,ws.title,cell.coordinate,after.coordinate])
                    if cell.data_type=='f':
                        if oldcache[ws.title][cell.coordinate].data_type=='e': original_errors.append([kind,ws.title,cell.coordinate,oldcache[ws.title][cell.coordinate].value])
                        if cached[ws.title][after.coordinate].data_type=='e': errors.append([kind,ws.title,after.coordinate,cached[ws.title][after.coordinate].value])
            original_merges=set()
            for merge in ws.merged_cells.ranges:
                a,b,c,d=merge.bounds
                if shifted: a+=a>=3;c+=c>=3
                original_merges.add(f'{get_column_letter(a)}{b}:{get_column_letter(c)}{d}')
            after_merges={str(m) for m in destination.merged_cells.ranges}
            if shifted: after_merges={m for m in after_merges if not re.fullmatch(r'C\d+:C\d+',m)}
            add(kind+'/'+ws.title+'原有合并保留',original_merges==after_merges,
                {'missing':sorted(original_merges-after_merges)[:5],'extra':sorted(after_merges-original_merges)[:5]})
            add(kind+'/'+ws.title+'表格对象保留',list(ws.tables)==list(destination.tables))
            add(kind+'/'+ws.title+'冻结设置保留',ws.freeze_panes==destination.freeze_panes)
    add('无未授权单元格值或公式变化',not diffs,{'count':len(diffs),'samples':diffs[:15]})
    native_styles=load(out/'native-style-checks.json') if (out/'native-style-checks.json').exists() else []
    native_hashes=load(out/'native-style-hashes.json') if (out/'native-style-hashes.json').exists() else {}
    same_style_files=all(native_hashes.get(k)==sha(plan[k+'_output']) for k in ['report','rainbow'])
    style_ok=not style_diffs or (native_styles and all(s['passed'] for s in native_styles)
                and sum(s['represented_cells'] for s in native_styles)==len(style_diffs) and same_style_files)
    add('原有单元格实际样式保留',style_ok,{'xml_normalization_cells':len(style_diffs),
        'native_style_pairs':len(native_styles),'native_failed_pairs':sum(not s['passed'] for s in native_styles)})
    mapped_errors={(kind,sn,shifted_address(a) if kind=='report' and sn=='SGD促销' else a,code)
                   for kind,sn,a,code in original_errors}
    new_errors=set(map(tuple,errors))-mapped_errors
    add('没有新增公式错误',not new_errors,{'existing':len(original_errors),'saved':len(errors),'new':sorted(new_errors)})
    rf,rv=books['report']; bf,bv=books['rainbow']
    add('保存并重开后主报价为1.70%',abs(rv['SGD促销']['C51'].value-float(plan['main_pct'])/100)<1e-12)
    add('保存并重开后最高报价为2.00%',abs(rv['最高报价汇总 ']['E10'].value-float(plan['highest_pct'])/100)<1e-12)
    add('保存并重开后三档明细完整',all(abs(bv['SGD Promotional Rate'].cell(18+i,8).value-float(d['rate_pct'])/100)<1e-12 for i,d in enumerate(plan['details'])))
    add('模拟插行未保存到交付副本',rf['SGD促销']['A54'].value=='BEA' and rf['SGD促销']['A111'].value=='SCB' and not any('仅内存回归测试' in str(c.value) for row in rf['SGD促销'] for c in row))
    run_path=Path(plan['source_run'])
    add('提取记录及5项待复核状态保持',sha(run_path/'run.json')==plan['run_sha256'] and sha(run_path/'result.json')==plan['result_sha256'])
    try:
        make_plan(load(run_path/'result.json'),{}, {},plan['report_template'],plan['rainbow_template'],out/'must-not-publish')
    except ValueError as exc:
        add('正式导出仍拒绝未复核报价','未解决复核项' in str(exc),str(exc))
    else:
        add('正式导出仍拒绝未复核报价',False)
    report={'checks':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks),
            'cell_differences':diffs,'style_differences':style_diffs,
            'original_formula_errors':original_errors,'saved_formula_errors':errors,'new_formula_errors':sorted(new_errors),
            'scope':'SCB frozen evidence only; unapproved validation copies',
            'output_files':[plan['report_output'],plan['rainbow_output']]}
    save(out/'table-validation-checks.json',report)
    rows=''.join('<tr><td>'+html.escape(c['name'])+'</td><td>'+('通过' if c['passed'] else '待修复')+'</td><td>'+html.escape(str(c['detail']))+'</td></tr>' for c in checks)
    markup='<!doctype html><meta charset="utf-8"><title>渣打插表验证</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;color:#17324b}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #ccd5dd}img{max-width:100%}aside{background:#fff2cc;padding:16px}</style><h1>渣打插表验证</h1><aside>基于9月16日模板及9月24日冻结证据。本次仅验证副本写入；5项原复核事项仍保留，尚未形成正式本期报价。</aside>'
    markup+=f'<p>检查通过 {report["passed"]}/{report["total"]}。原有公式错误：{len(original_errors)}处；保存后：{len(errors)}处。未改动无关原始公式。</p><p>彩虹表顺序在生成时按Personal及上期并列顺序确定。手动修改明细利率会重算显示值；需要重新生成才能重新排序。</p>'
    for name in ['native-report-after','native-summary-after','native-rainbow-after']:
        markup+=f'<img src="{name}.png" alt="Excel实际输出预览">'
    markup+='<table><tr><th>检查项目</th><th>结果</th><th>说明</th></tr>'+rows+'</table>'
    (out/'table-validation.html').write_text(markup,encoding='utf8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'value_diffs':len(diffs),'style_xml_differences':len(style_diffs),'old_formula_errors':len(original_errors),'saved_formula_errors':len(errors),'introduced_formula_errors':len(new_errors)},ensure_ascii=False))
    if any(not c['passed'] for c in checks): raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);check(p.parse_args().plan)

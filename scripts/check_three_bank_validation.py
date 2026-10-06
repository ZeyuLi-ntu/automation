"""Read-only saved-file validation, using the bundled spreadsheet runtime."""
import argparse
from collections import defaultdict
from copy import copy
import html
from pathlib import Path
import re
import openpyxl
from openpyxl.formula import Tokenizer
from openpyxl.utils import get_column_letter,column_index_from_string
from market_rates.common import load,save
from market_rates.table_validation import sha
from market_rates.export import make_plan
from xml.etree.ElementTree import tostring

def icon_cells(sheet):
    result=defaultdict(set)
    for region in sheet.conditional_formatting:
        icons=[tostring(rule.iconSet.to_tree()) for rule in sheet.conditional_formatting[region] if rule.type=='iconSet']
        if not icons:continue
        for area in region.sqref.ranges:
            for row in range(area.min_row,area.max_row+1):
                for col in range(area.min_col,area.max_col+1):result[(row,col)].update(icons)
    return result

def moved(row,plan):return row+sum(i['count'] for i in plan['report_inserts'] if i['at']<=row)
def formula_after(formula,plan,own=False):
    tokens=Tokenizer(formula).items
    for t in tokens:
        if t.type!='OPERAND' or t.subtype!='RANGE':continue
        if '!' in t.value:prefix,ref=t.value.rsplit('!',1);applies=prefix.strip("'")=='SGD促销'
        else:prefix,ref=None,t.value;applies=own
        if not applies:continue
        def transform(m):
            col=column_index_from_string(m[2]);row=int(m[4])
            return m[1]+get_column_letter(col+(col>=3)*plan.get('date_column_shift',1))+m[3]+str(moved(row,plan))
        ref=re.sub(r'(\$?)([A-Z]{1,3})(\$?)(\d+)',transform,ref)
        t.value=(prefix+'!' if prefix is not None else '')+ref
    return '='+''.join(t.value for t in tokens)

STYLE={}
def style(c):
    key=(id(c.parent.parent),tuple(c._style or ()))
    if key not in STYLE:STYLE[key]=tuple(copy(getattr(c,k)) for k in ['font','fill','border','alignment','protection'])+(c.number_format,)
    return STYLE[key]

def check(path):
    plan=load(path);out=Path(path).resolve().parent;checks=load(out/'native-checks.json');diffs=[];style_pairs={};errors=[];old_errors=[];old_formula_errors=0;history_diffs=[]
    date_shift=plan.get('date_column_shift',1)
    def add(name,ok,detail=''):checks.append(dict(name=name,passed=bool(ok),detail=detail))
    edited_b={u['start']+i for u in plan['report_updates'] if u['group'] for i in range(min(len(u['group']['details']),u['end']-u['start']+1))}
    edited_b.update(u['start'] for u in plan['report_updates'] if u.get('missing_status'))
    summary_cells={f'{get_column_letter(v["col"])}{v["row"]}' for v in plan['summary']}|{'B2'}
    deltas={v['source']:v for v in plan.get('deltas',[])}
    cached_books={}
    for kind in ['report','rainbow']:
        a=openpyxl.load_workbook(plan[kind+'_template']);b=openpyxl.load_workbook(plan[kind+'_output'])
        ac=openpyxl.load_workbook(plan[kind+'_template'],data_only=True);bc=openpyxl.load_workbook(plan[kind+'_output'],data_only=True);cached_books[kind]=bc
        add(kind+' 原始文件未修改',sha(plan[kind+'_template'])==plan[kind+'_sha256'])
        add(kind+' 工作表名称与顺序保持',b.sheetnames==a.sheetnames+[plan['input_sheet']])
        if kind=='report':
            old_icons=icon_cells(a['SGD促销']);new_icons=icon_cells(b['SGD促销'])
            bad_quotes=[f'C{r}' for r,c in new_icons if c==3]
            add('保存后的本期利率无箭头',not bad_quotes,bad_quotes)
            missing_icons=[]
            for (r,c),rules in old_icons.items():
                if c==3 and date_shift==0:continue
                target=(moved(r,plan),c+(date_shift if c>=3 else 0))
                if not rules.issubset(new_icons.get(target,set())):missing_icons.append([r,c,*target])
            add('历史及涨跌栏箭头规则保留',not missing_icons,missing_icons[:10])
        for ws in a:
            dest=b[ws.title];shift=kind=='report' and ws.title=='SGD促销';rb=kind=='rainbow' and ws.title=='SGD Promotional Rate'
            add(kind+'/'+ws.title+' 表格对象保留',list(ws.tables)==list(dest.tables))
            add(kind+'/'+ws.title+' 冻结设置保留',ws.freeze_panes==dest.freeze_panes)
            for row in ws:
                for cell in row:
                    target=dest.cell(moved(cell.row,plan) if shift else cell.row,cell.column+date_shift if shift and cell.column>=3 else cell.column)
                    if rb and (cell.coordinate=='A1' or cell.row>=3):continue
                    if shift and (cell.coordinate=='A1' or cell.column==2 and cell.row in edited_b):continue
                    if shift and date_shift==0 and cell.column==3:continue
                    if shift and cell.column==1 and any(m['start']<=target.row<=m['end'] for m in plan.get('bank_merges',[])):continue
                    if kind=='report' and ws.title=='最高报价汇总 ' and cell.coordinate in summary_cells:continue
                    expected=formula_after(cell.value,plan,shift) if kind=='report' and cell.data_type=='f' else cell.value
                    if shift and cell.coordinate in deltas:expected=deltas[cell.coordinate]['formula']
                    if expected!=target.value:diffs.append([kind,ws.title,cell.coordinate,target.coordinate,str(expected),str(target.value)])
                    if shift and cell.column>=3+(date_shift==0) and cell.coordinate not in deltas:
                        old=ac[ws.title][cell.coordinate].value;new=bc[ws.title][target.coordinate].value
                        if old!=new and not (isinstance(old,(int,float)) and isinstance(new,(int,float)) and abs(old-new)<1e-12):history_diffs.append([cell.coordinate,target.coordinate,str(old),str(new)])
                    if style(cell)!=style(target):
                        k=(kind,ws.title,cell.style_id,target.style_id,type(cell).__name__,type(target).__name__)
                        if k not in style_pairs:style_pairs[k]=dict(kind=kind,sheet=ws.title,source=cell.coordinate,target=target.coordinate,represented_cells=0)
                        style_pairs[k]['represented_cells']+=1
                    if ac[ws.title][cell.coordinate].data_type=='e':
                        old_errors.append((kind,ws.title,target.coordinate,ac[ws.title][cell.coordinate].value))
                        old_formula_errors+=cell.data_type=='f'
            for row in bc[ws.title]:
                for cell in row:
                    if cell.data_type=='e':errors.append((kind,ws.title,cell.coordinate,cell.value))
            if not rb:
                expected_merges=set()
                for m in ws.merged_cells.ranges:
                    c1,r1,c2,r2=m.bounds
                    if shift and c1==c2==2 and r1 in edited_b:continue
                    if shift and date_shift==0 and c1==c2==3:continue
                    if shift:c1+=(c1>=3)*date_shift;c2+=(c2>=3)*date_shift;r1=moved(r1,plan);r2=moved(r2,plan)
                    if shift and c1==c2==1:
                        for bank_merge in plan.get('bank_merges',[]):
                            if bank_merge['start']==r1:r2=bank_merge['end']
                    expected_merges.add(f'{get_column_letter(c1)}{r1}:{get_column_letter(c2)}{r2}')
                actual={str(m) for m in dest.merged_cells.ranges}
                add(kind+'/'+ws.title+' 历史合并区域保留',not(expected_merges-actual),list(expected_merges-actual)[:5])
        add(kind+' 无新公式错误',not(set(errors)-set(old_errors)),list(set(errors)-set(old_errors))[:8])
    add('原有受保护单元格值和公式一致',not diffs,dict(count=len(diffs),samples=diffs[:10]))
    add('滚动后历史缓存值保持',not history_diffs,dict(count=len(history_diffs),samples=history_diffs[:10]))
    report=cached_books['report']['SGD促销']
    for d in plan.get('deltas',[]):
        now,old=report.cell(d['row'],3).value,report.cell(d['row'],4).value
        value=report.cell(d['row'],d['col']).value
        expected=now-old if isinstance(now,(float,int)) and isinstance(old,(float,int)) else '-'
        add('保存后的最新两期变动 '+d['source'],value==expected if isinstance(expected,str) else isinstance(value,(float,int)) and abs(value-expected)<1e-12,value)
    excluded=set(plan.get('workbook_policy',{}).get('deferred_product_ids',[]))
    add('暂缓产品不进入输入和汇总',not any(r['product_id'] in excluded for r in plan['details']))
    if 'boc-sgd-welcome' in excluded:
        leaks=[]
        for kind,names in [('report',['SGD促销','最高报价汇总 ',plan['input_sheet']]),('rainbow',['SGD Promotional Rate',plan['input_sheet']])]:
            for name in names:
                for row in cached_books[kind][name]:
                    for cell in row:
                        if isinstance(cell.value,str) and any(term in cell.value for term in ('boc-sgd-welcome','新客户促销')):leaks.append([kind,name,cell.coordinate])
        add('中行新客户促销在生成表格中全部排除',not leaks,leaks)
    add('新增产品均处于原银行合并区',all(any(m['bank']==i['group']['bank'] and m['start']<=i['target_start'] and m['end']>=i['target_start']+i['count']-1 for m in plan.get('bank_merges',[])) for i in plan['report_inserts']))
    for i in plan['report_inserts']:
        s=cached_books['report']['SGD促销'];cells=[s.cell(r,c).value for r in range(i['target_start'],i['target_start']+i['count']) for c in range(4,plan.get('report_last_col',243)+1)]
        add('新增产品历史为空 '+i['group']['id'],all(v is None for v in cells))
    for g in plan['groups']:
        value=cached_books['report']['SGD促销'].cell(g['report_row'],3).value
        add('保存后的调研主报价 '+g['id'],abs(value-float(g['main_pct'])/100)<1e-12,value)
    rb=cached_books['rainbow']['SGD Promotional Rate'];baseline=openpyxl.load_workbook(plan['rainbow_template'],data_only=True)['SGD Promotional Rate']
    for rg in plan['rainbow_groups']:
        last=None;ties=[]
        for block in rg['blocks']:
            rate=float(block.get('bank_rank_rate',block['rank_rate']));add('排序 '+rg['tenor']+'/'+block['bank'],last is None or last>=rate);last=rate
            if 'group' in block:
                for n,d in enumerate(block['group']['details']):
                    cell=rb.cell(block['target_start']+n,rg['col']+1)
                    add('保存后的彩虹表报价 '+d['product_id']+'/'+str(d['tenor_value'])+'/'+str(d['input_row']),abs(cell.value-float(d['rate_pct'])/100)<1e-12)
                    add('期限颜色 '+cell.coordinate,cell.fill.fgColor.rgb[-6:]==baseline.cell(3,rg['col']+1).fill.fgColor.rgb[-6:])
                    if d['amount_max'] and float(d['amount_max'])%1:
                        text=rb.cell(block['target_start']+n,rg['col']+2).value or ''
                        add('金额边界小数完整显示 '+cell.coordinate,format(float(d['amount_max']),',.2f') in text,text)
            elif block.get('source_start'):
                actual=[[rb.cell(block['target_start']+n,c).value for c in range(rg['col'],rg['col']+3)] for n in range(len(block['rows']))]
                add('其他银行明细保留 '+rg['tenor']+'/'+block['bank'],actual==block['rows'])
        names=[rb.cell(r,rg['col']).value for r in range(3,rg['last_row']+1) if rb.cell(r,rg['col']).value]
        add('同期限银行名称仅出现一次 '+rg['tenor'],len(names)==len(set(names)))
    run=Path(plan['source_run']);add('原始提取与待复核状态未被插表修改',sha(run/'run.json')==plan['run_sha256'] and sha(run/'result.json')==plan['result_sha256'])
    try:make_plan(load(run/'result.json'),load(run/'config.snapshot.json'),{},plan['report_template'],plan['rainbow_template'],out/'forbidden');guard=False
    except ValueError as exc:guard='未解决复核项' in str(exc)
    add('待复核报价仍被正式导出拦截',guard)
    save(out/'style-samples.json',list(style_pairs.values()))
    native=load(out/'native-style-checks.json') if (out/'native-style-checks.json').exists() else []
    hashes=load(out/'native-style-hashes.json') if (out/'native-style-hashes.json').exists() else {}
    add('原表有效样式保持',not style_pairs or (bool(native) and all(s['passed'] for s in native) and sum(s['represented_cells'] for s in native)==sum(s['represented_cells'] for s in style_pairs.values()) and all(hashes.get(k)==sha(plan[k+'_output']) for k in ['report','rainbow'])),dict(pairs=len(style_pairs),verified=len(native)))
    result=dict(checks=checks,passed=sum(c['passed'] for c in checks),total=len(checks),differences=diffs,
                source_error_cells=len(old_errors),source_formula_errors=old_formula_errors,saved_error_cells=len(errors),new_errors=list(set(errors)-set(old_errors)))
    save(out/'table-validation-checks.json',result)
    body=['<!doctype html><meta charset="utf-8"><style>body{font:16px Arial;max-width:1180px;margin:35px auto;line-height:1.6}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:7px}img{max-width:100%}.note{background:#fff3cd;padding:15px}</style><h1>'+html.escape(plan['collection_label'])+' · 插表验证</h1>',
          f'<p>{result["passed"]}/{result["total"]} 项通过。本次表内 {len(plan["details"])} 条报价、{len(plan["groups"])} 个产品与期限组合；未批准发布。</p>',
          '<p>当日变动始终比较最新两列；本期报价栏不显示涨跌箭头。暂不纳入 CIMB Why Wait、Preferred 迎新、HLF Digital 及 BOC 新客户促销。新增档位保持在原银行合并区。</p>',
          '<p>MariBank、Trust 已按要求退出后续调研范围。Maybank 本期产品、金额门槛、文字、截图与采集时间见输入明细及原始证据。</p>' if 'Maybank' in plan['bank_dates'] else '',
          '<p>证据日期：'+html.escape('；'.join(b+' '+d for b,d in plan['bank_dates'].items()))+'。汇编日期：'+plan['as_of']+'。</p>',
          '<p class="note">本次覆盖 '+html.escape('、'.join(plan['banks']))+' 的 SGD 促销。彩虹表其余银行保留底稿，不能视为全市场最新排名。完整条款和两路差异仍须人工复核。同一本地模型的两路一致不保证准确。修改输入会重算数值；变更排序需重新生成。</p>',
          '<p>历史底稿日期：'+html.escape(plan.get('baseline_date','2026-09-16'))+'；本次处理：'+('同日修订，更新当前列' if date_shift==0 else '新增日期列，保留已确认历史')+'。人工修正延续 '+str(len(plan.get('manual_applied',[])))+' 条。中行 2M、5M 及 CITI 2M 投资搭配促销本轮仅保留采集明细。</p>',
          '<p>工行原页未明示年化单位，已保留为计息口径待人工核实；未把两路一致当成该口径已确认。</p>' if 'ICBC' in plan['banks'] else '',
          f'<p>原表错误单元格 {len(old_errors)} 处（其中公式缓存错误 {old_formula_errors} 处）；验证副本新增 {len(result["new_errors"])} 处。</p>',
          '<p><a href="'+run.as_uri()+'/review.html">合并报价复核</a> · <a href="'+run.as_uri()+'/evidence/index.html">原始证据</a></p>',
          '<p>'+ ' · '.join('<a href="'+Path(plan[k+'_output']).name+'">'+v+'</a>' for k,v in [('report','调研工作簿'),('rainbow','彩虹表工作簿')])+'</p>']
    body.append('<p><a href="http://127.0.0.1:8765">人工修正入口</a>（先双击项目目录里的“人工修正入口.cmd”）</p>')
    if plan.get('coverage'):
        body.append('<h2>未填数值的银行</h2><p>这些状态不代表产品已停止提供；未使用旧利率或挂牌利率补齐。</p><table><tr><th>银行</th><th>本期状态</th><th>证据／尝试日期</th></tr>')
        for c in plan['coverage']:
            body.append('<tr><td>'+html.escape(c['bank'])+'</td><td>'+html.escape(c['reason'])+'</td><td>'+html.escape(c.get('checked_at',''))+'</td></tr>')
        body.append('</table><p>Singapura Finance 中秋额外奖励已于 2026-09-26 结束，本期未纳入；普通促销仍单独核验。各银行使用表中标明日期的证据，不能将本次汇编日期视为所有页面的重新采集日期。</p>')
    for source in plan.get('source_runs',[]):
        directory=Path(source['path']);kind=source['qualification']['kind']
        page='benchmark.html' if kind=='frozen_source_reference' else 'agreement.html'
        label={'frozen_source_reference':'原文基准核验','dual_agreement_imported_evidence':'官网文字与用户截图双路一致，自动采集未验证'}.get(kind,'双路一致检查，需人工核验')
        body.append('<p>'+html.escape(' / '.join(source['banks'])+'：'+label)+' · <a href="'+directory.as_uri()+'/'+page+'">原始提取检查</a> · <a href="'+directory.as_uri()+'/review.html">本批复核</a></p>')
    body.append('<table><tr><th>检查</th><th>结果</th></tr>')
    body += ['<tr><td>'+html.escape(c['name'])+'</td><td>'+('通过' if c['passed'] else '待修复')+'</td></tr>' for c in checks]
    body.append('</table>')
    weekly=out/'weekly-history-checks.json'
    if weekly.exists():
        record=load(weekly)
        body.append('<h2>连续两期历史滚动验证</h2><p>使用独立合成测试数据，连续两期检查历史值、独立明细引用及产品位置；未改变正式历史底稿。</p>')
        for period in record['periods']:
            v=period['verification'];body.append('<p>第 '+str(period['week'])+' 期：'+str(v['history_cells_checked'])+' 个历史单元格，'+('通过' if v['passed'] else '待修复')+'。</p>')
        body.append('<p><a href="weekly-history-checks.json">滚动验证记录（合成测试，非未来实际报价）</a></p>')
    for name in ['quote-maybank-9m','quote-maybank-12m','quote-uob-12m','quote-boc-3m','quote-boc-9m','delta-after','report-after','summary-after','rainbow-1m','rainbow-3m','rainbow-6m-top','rainbow-6m-bottom','rainbow-9m','rainbow-12m','rainbow-18m','rainbow-24m']:
        if not (out/(name+'.png')).exists():continue
        body.append('<h2>'+name+'</h2><img src="'+name+'.png">')
    (out/'table-validation.html').write_text(''.join(body),encoding='utf8')
    print(dict(passed=result['passed'],total=result['total'],value_diffs=len(diffs),new_errors=len(result['new_errors']),style_pairs=len(style_pairs)))
    if result['passed']!=result['total']:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);check(p.parse_args().plan)

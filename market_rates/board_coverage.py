"""Required board scope comes from dated Bank List cells, never observed offers.

Presence, saved output, evidence qualification and human acceptance are distinct.
This audit measures bank/currency availability; it does not certify every source
product/tenor/tier merely because one rate for that pair was found.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import hashlib
import html
import re
import os
from urllib.parse import quote
from .common import load, save
from .xlsx_read import read_xlsx
from .workbook_policy import bank_in_scope, presentation_currency

ROOT = Path(__file__).resolve().parents[1]
CURRENCIES = ['SGD','USD','CNY','AUD','NZD','CAD','HKD','EUR','GBP']
HEADERS = dict(zip(['新元挂牌','美元挂牌','人民币挂牌','澳元挂牌','新西兰元挂牌','加元挂牌','港币挂牌','欧元挂牌','英镑挂牌'], CURRENCIES))
LABELS = {'missing': '尚未抓取', 'held': '缺少必要信息，未写入', 'partial': '部分已写入',
          'present': '已有数值写入', 'write_gap': '插表缺失'}


def canonical_bank(value):
    value = str(value or '').strip()
    return 'DBS' if value in ['DBS/POSB','POSB'] else value


def dated(value):
    """A date is a scope marker, not evidence that a quote was checked that day."""
    if isinstance(value, (date, datetime)): return True
    text = str(value or '').strip()
    for fmt in ['%Y%m%d','%Y-%m-%d','%Y/%m/%d']:
        try:
            parsed = datetime.strptime(text,fmt)
            if 2000 <= parsed.year <= 2100: return True
        except ValueError: pass
    try:
        n = float(text)
        return n.is_integer() and 36526 <= n <= 73415
    except ValueError: return False


def required_scope(workbook):
    book = read_xlsx(workbook, merge_anchors_only=True)
    if 'Bank List' not in book: raise ValueError('缺少 Bank List，不能推断应有挂牌范围')
    cells = book['Bank List']; columns = {}
    bank_col = next((re.sub(r'\d+$','',a) for a,v in cells.items() if a.endswith('1') and v=='Bank List'),None)
    if not bank_col: raise ValueError('Bank List 银行列缺失')
    for addr,value in cells.items():
        if not re.fullmatch(r'[A-Z]+1',addr): continue
        if value in HEADERS: columns[addr[:-1]] = HEADERS[value]
        elif '挂牌' in str(value): raise ValueError('未识别挂牌币种列：'+str(value))
    if set(columns.values()) != set(CURRENCIES): raise ValueError('Bank List 挂牌列不完整')
    result=[];seen=set()
    for addr,bank_label in cells.items():
        if not re.fullmatch(bank_col+r'\d+',addr) or addr==bank_col+'1': continue
        bank=canonical_bank(bank_label);row=int(re.search(r'\d+$',addr)[0])
        if not bank_in_scope(bank): continue
        for col,cur in columns.items():
            marker=cells.get(col+str(row))
            if marker in [None,'']: continue
            if not dated(marker): raise ValueError('Bank List!'+col+str(row)+' 的范围标记不是有效日期')
            if (bank,cur) in seen: raise ValueError('Bank List 重复银行/币种：'+bank+'/'+cur)
            seen.add((bank,cur))
            result.append(dict(bank=bank,bank_label=str(bank_label),currency=cur,
                cell=col+str(row),marker=str(marker),sheet=cur+'挂牌'))
    if not result: raise ValueError('Bank List 未找到有日期的挂牌范围')
    return result


def numeric(value):
    if value is None or isinstance(value,bool): return False
    return bool(re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',str(value).strip()))


def column(number):
    value=''
    while number:
        number,r=divmod(number-1,26);value=chr(65+r)+value
    return value


def output_cells(plan, book=None):
    """Locate current rates only: historical values and input sheets do not count."""
    values=defaultdict(list)
    for matrix in plan.get('matrices',[]):
        cur=matrix['currency'];sheet=matrix['sheet']
        for group in matrix['groups']:
            for j,row in enumerate(group['rows']):
                for cell in row['values']:
                    addr=column(cell['col'])+str(group['target_row']+j)
                    value=book.get(sheet,{}).get(addr) if book is not None else cell['expected']
                    if numeric(value): values[(canonical_bank(group['bank']),cur)].append(dict(sheet=sheet,cell=addr,value=str(value)))
    for history in plan.get('histories',[]):
        cur=history['currency'];sheet=history['sheet'];cc=history['current_col']
        # Planned writes carry their bank identity; do not count unmodified old
        # history cells or a numeric date header as a current quotation.
        cells=[(r['bank'],r['address'],r['expected']) for r in history['existing']]
        cells += [(i['bank'],column(cc)+str(i['target_row']+j),r['expected']) for i in history['inserts'] for j,r in enumerate(i['rows'])]
        for bank,addr,expected in cells:
            value=book.get(sheet,{}).get(addr) if book is not None else expected
            if numeric(value): values[(canonical_bank(bank),cur)].append(dict(sheet=sheet,cell=addr,value=str(value)))
    return values


def reason_summary(rows):
    return dict(Counter(d.get('hold_reason') or '未提供拦截原因' for d in rows if not d['insertable']))


def audit(plan, workbook=None, *, inspect_saved=True, investigations=None):
    workbook=Path(workbook or ROOT.parent/'20260916市场利率调研.xlsx')
    required=required_scope(workbook);records=defaultdict(list)
    for d in plan.get('details',[]):
        records[(canonical_bank(d['bank']),presentation_currency(d['currency']))].append(d)
    saved_path=Path(plan.get('report_output',''))
    saved=read_xlsx(saved_path,merge_anchors_only=True) if inspect_saved and saved_path.is_file() else None
    outputs=output_cells(plan,saved);notes={}
    if investigations and investigations.get('source_run')==plan.get('source_run'):
        notes={(r['bank'],r['currency']):r for r in investigations['items']}
    rows=[]
    for target in required:
        pair=target['bank'],target['currency'];ds=records.get(pair,[]);usable=[d for d in ds if d['insertable']]
        status='missing' if not ds else 'held' if not usable else 'partial' if len(usable)<len(ds) else 'present'
        if usable and not outputs.get(pair): status='write_gap'
        missing_reason='尚未从官网读入本期数据' if not ds else ''
        evidence=notes.get(pair,{})
        rows.append(dict(target,status=status,status_label=LABELS[status],detail_count=len(ds),insertable_count=len(usable),
            held_count=len(ds)-len(usable),hold_reasons=reason_summary(ds),missing_reason=missing_reason,
            output_numeric_count=len(outputs.get(pair,[])),output_cells=outputs.get(pair,[]),
            human_accepted_count=sum(bool(d.get('manual_reviewed')) for d in ds),
            evidence_dates=sorted({d.get('evidence_date','未记录') for d in ds}),investigation=evidence))
    counts=Counter(r['status'] for r in rows);required_pairs={(r['bank'],r['currency']) for r in rows}
    available=sum(bool(r['output_numeric_count']) and bool(r['insertable_count']) for r in rows)
    return dict(version=1,as_of=plan['as_of'],generated_at=datetime.now().astimezone().isoformat(),
        scope_workbook=str(workbook.resolve()),scope_sha256=hashlib.sha256(workbook.read_bytes()).hexdigest(),
        report=str(saved_path),report_sha256=hashlib.sha256(saved_path.read_bytes()).hexdigest() if saved is not None else None,
        saved_output_inspected=saved is not None,source_run=plan.get('source_run'),
        required_count=len(rows),bank_count=len({r['bank'] for r in rows}),counts=dict(counts),
        pairs_with_numeric_output=available,missing_or_fully_held=len(rows)-available,
        required_pair_availability_complete=available==len(rows),
        completeness_claim='仅检查要求覆盖的银行/币种及当前输出数值，不把存在一条报价称为全产品、期限、档位完整。',
        rows=rows,extra_pairs=[dict(bank=b,currency=c,count=len(ds)) for (b,c),ds in sorted(records.items()) if (b,c) not in required_pairs],
        excluded_banks=['MARI','TRUST'],excluded_currencies=['JPY'],currency_mapping={'CNH':'CNY'})


def html_report(result):
    esc=lambda x:html.escape(str(x))
    rows=result['rows'];by_pair={(r['bank'],r['currency']):r for r in rows}
    gap=result['missing_or_fully_held'];checked='已回读保存的工作簿' if result['saved_output_inspected'] else '仅检查插表计划'
    body=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>挂牌覆盖检查</title>',
        '<style>body{font:15px "Microsoft YaHei",sans-serif;line-height:1.65;margin:30px;color:#213547}h1{margin-bottom:5px}table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #cfd8df;padding:9px}th{background:#eaf0f5;text-align:left}small{display:block;color:#526674}.missing,.write_gap{background:#fee3e0}.held{background:#fff0d5}.partial{background:#fcf5bd}.present{background:#e3f2e9}.na{background:#f3f4f6;color:#89929b}.matrix td{font-size:13px;white-space:nowrap}.warn{color:#9b3026}a{color:#126297}details{border:1px solid #ccd6df;padding:12px;margin:9px 0}summary{cursor:pointer;font-weight:600}.scroll{overflow:auto}</style>',
        '<h1>挂牌覆盖检查</h1><p>依据原始 Bank List 中填写日期的挂牌单元格；不按已采集数据反推范围。</p>',
        f'<p><b>{result["bank_count"]} 家 · 应有 {result["required_count"]} 组 · 已有当前数值 {result["pairs_with_numeric_output"]} 组 · 缺当前数值 {gap} 组</b><br>{esc(checked)}；工作簿期次 {esc(result["as_of"])}。日期格表示应有范围，不表示本期已核验。</p>',
        '<p class="warn">数字检查通过 ≠ 覆盖齐全；“已有数值写入” ≠ 全部产品、期限、金额档位已经完整。通过自动核验的数据直接写入Excel。</p>',
        '<p>绿色：已有数值；黄色：部分档位可用；橙色：已读到明细但缺少必要信息；红色：尚未抓取或插表缺失；灰色：Bank List 未要求。</p>',
        '<div class="scroll"><table class="matrix"><thead><tr><th>银行</th>'+''.join('<th>'+c+'</th>' for c in CURRENCIES)+'</tr></thead><tbody>']
    for bank in dict.fromkeys(r['bank'] for r in rows):
        label=next(r['bank_label'] for r in rows if r['bank']==bank)
        line='<tr><th>'+esc(label)+'</th>'
        for cur in CURRENCIES:
            r=by_pair.get((bank,cur))
            line+=('<td class="'+r['status']+'"><a href="#'+esc(bank.replace(' ','_')+'-'+cur)+'">'+esc(r['status_label'])+'</a><small>'+esc(r['cell'])+' · '+str(r['insertable_count'])+'/'+str(r['detail_count'])+' 条</small></td>') if r else '<td class="na">—</td>'
        body.append(line+'</tr>')
    body.append('</tbody></table></div><p>每格的条数为可插表明细数 / 当前活动明细数；空白要求格不擅自扩大为缺失。MariBank、Trust、JPY 继续排除，CNH 按 CNY。</p><h2>逐项原因与定位</h2>')
    for r in sorted(rows,key=lambda r:({'missing':0,'write_gap':0,'held':1,'partial':2,'present':3}[r['status']],r['bank'],CURRENCIES.index(r['currency']))):
        issue=r['investigation'];addr=r['bank'].replace(' ','_')+'-'+r['currency']
        body.append('<details id="'+esc(addr)+'"'+(' open' if r['status'] not in ['present'] else '')+'><summary>'+esc(r['bank_label']+' / '+r['currency']+'：'+r['status_label'])+'</summary>')
        body.append('<p>范围：Bank List!'+esc(r['cell'])+'；活动明细 '+str(r['detail_count'])+' 条，可插表 '+str(r['insertable_count'])+' 条；当前输出数值 '+str(r['output_numeric_count'])+' 格；人工已确认 '+str(r['human_accepted_count'])+' 条。</p>')
        if r['missing_reason']:body.append('<p>'+esc(r['missing_reason'])+'</p>')
        for reason,n in r['hold_reasons'].items():body.append('<p>'+esc(reason)+'：'+str(n)+' 条</p>')
        if issue:
            body.append('<p>'+esc(issue.get('finding',''))+'</p><p>处理：'+esc(issue.get('next_action',''))+'</p>')
            for evidence in issue.get('evidence',[]):
                link=quote(os.path.relpath(Path(evidence['path']).resolve(),Path(result['report']).parent).replace('\\','/'))
                body.append('<p><a href="'+esc(link)+'">'+esc(evidence['label'])+'</a></p>')
            for url in issue.get('urls',[]):body.append('<p><a href="'+esc(url)+'">银行来源</a></p>')
        if r['output_cells']:
            body.append('<p>当前数值位置示例：'+esc('，'.join(c['sheet']+'!'+c['cell'] for c in r['output_cells'][:8]))+'；实际采集日：'+esc(' / '.join(r['evidence_dates']))+'。</p>')
        body.append('</details>')
    body.append('<p>检查期间仅补取来源调查证据。尚未完成新数据双路核验、字段整理和插表的组合，不会被改成“已完成”。</p></html>')
    return ''.join(body)


def write_audit(plan,out,*,workbook=None,inspect_saved=True,investigations=None):
    result=audit(plan,workbook,inspect_saved=inspect_saved,investigations=investigations)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    save(out/'board-coverage.json',result)
    (out/'board-coverage.html').write_text(html_report(result),encoding='utf8')
    return result

"""Non-publishing SCB template validation: no approval or production state changes."""
from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
from .common import load, save
from .schema import FACTS
from .rules import build_views
from .xlsx_read import read_xlsx


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stable_blocks(blocks):
    """Rank by each block's selected Personal value; equal values keep prior order."""
    return sorted(deepcopy(blocks), key=lambda b: (-Decimal(str(b['rank_rate'])), b['prior_index']))


def make_validation_plan(run_folder, report, rainbow, output):
    run_folder, report, rainbow, output = map(Path, (run_folder, report, rainbow, output))
    run = load(run_folder / 'run.json')
    config = load(run_folder / 'config.snapshot.json')
    assessment = load(run_folder / 'result.json')
    if not run.get('pilot', {}).get('no_publication') or assessment['pending'] <= 0:
        raise ValueError('此入口仅用于有待复核项的非发布试点副本；不能用于正式导出')
    rows = run['llm']['offers']
    if len(rows) != 3 or any(r['bank'] != 'SCB' or r['product_id'] != 'scb-sgd-fresh-funds' for r in rows):
        raise ValueError('试点产品范围不匹配')
    compared = [f for f in FACTS if f != 'conditions']
    for row in rows:
        matches = [r for r in run['vlm']['offers'] if r['audience'] == row['audience']]
        if len(matches) != 1 or any(row[f] != matches[0][f] for f in compared):
            raise ValueError('两路核心字段尚不一致，不能进行该副本的数值写入验证')
    if len(run['vlm']['offers']) != len(rows):
        raise ValueError('两路报价行数不一致')
    group = build_views(rows, config, {}, run['as_of'])['groups']
    if len(group) != 1 or group[0]['display_tenor'] != '6M':
        raise ValueError('本次模板验证仅登记SCB的6个月产品')
    group = group[0]
    rbook, rbbook = read_xlsx(report), read_xlsx(rainbow)
    sheet = rbook['SGD促销']; rs = rbbook['SGD Promotional Rate']
    expected = {'A48': '6 Months', 'A51': 'SCB', 'A54': 'BEA'}
    if any(sheet.get(a) != v for a,v in expected.items()):
        raise ValueError('渣打6个月银行块位置变化，必须重新检查模板映射')
    if rbook['最高报价汇总 '].get('B10') != 'SCB' or rs.get('G18') != 'SCB':
        raise ValueError('汇总或彩虹表的渣打位置变化')
    blocks = []
    for rownum in range(3,45):
        bank = rs.get(f'G{rownum}')
        if bank:
            blocks.append({'bank': bank, 'prior_index': len(blocks), 'source_start': rownum,
                           'rank_rate': rs.get(f'H{rownum}'), 'rows': []})
        blocks[-1]['rows'].append([rs.get(f'G{rownum}'), rs.get(f'H{rownum}'), rs.get(f'I{rownum}')])
    selected = next(b for b in blocks if b['bank'] == 'SCB')
    selected['rank_rate'] = str(Decimal(group['main_pct']) / 100)
    selected['details'] = group['details']
    ordered = stable_blocks(blocks)
    # In this frozen regression, the published order should remain unchanged.
    rownum = 3
    for block in ordered:
        block['target_start'] = rownum
        rownum += len(block['rows'])
    current_cells = [a for a,v in sheet.items() if a.startswith('C') and a[1:].isdigit() and v is not None]
    formula_cells = read_xlsx(report, formulas=True)['SGD促销']
    date_rows = [int(a[1:]) for a,v in sheet.items() if a.startswith('A') and a[1:].isdigit() and v == '日期']
    output.mkdir(parents=True, exist_ok=True)
    plan = {'mode': 'validation_only', 'source_run': str(run_folder.resolve()), 'source_pending': assessment['pending'],
            'run_sha256': sha(run_folder/'run.json'), 'result_sha256': sha(run_folder/'result.json'),
            'report_template': str(report.resolve()), 'rainbow_template': str(rainbow.resolve()),
            'report_sha256': sha(report), 'rainbow_sha256': sha(rainbow), 'as_of': run['as_of'],
            'report_output': str((output/'20260924_渣打插表验证_调研副本.xlsx').resolve()),
            'rainbow_output': str((output/'20260924_渣打插表验证_彩虹表副本.xlsx').resolve()),
            'main_pct': group['main_pct'], 'highest_pct': group['highest_pct'],
            'details': group['details'], 'current_cells': current_cells, 'date_rows': date_rows,
            'original_current_formula_count': len([v for v in formula_cells.values() if str(v).startswith('=')]),
            'rainbow_blocks': ordered, 'report_rows': [51,52,53], 'input_sheet': '插表验证明细',
            'summary_cell': 'E10', 'original_summary_date': rbook['最高报价汇总 '].get('F2'),
            'source_urls': [p['url'] for p in run['pages']],
            'notice': '仅SCB插表验证；报价尚待人工复核。其余银行与币种保留原期数据。'}
    save(output/'table-validation-plan.json', plan)
    return plan

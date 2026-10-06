"""Read current user-maintained bank URLs without modifying the source workbook."""
from pathlib import Path
import re
from urllib.parse import urlsplit
from .xlsx_read import read_xlsx,read_hyperlinks
from .scope import bank_name


def entries(path):
    book=read_xlsx(path,merge_anchors_only=True);hyperlinks=read_hyperlinks(path);records=[]
    for sheet,cells in book.items():
        bank=currency=None
        for row in range(2,max(int(re.search(r'\d+',k)[0]) for k in cells)+1):
            if cells.get(f'A{row}'):bank=bank_name(cells[f'A{row}']);currency=None
            currency=cells.get(f'B{row}') or currency
            category={'促销':'promo','挂牌':'board','board':'board'}.get(cells.get(f'C{row}'))
            if not bank or not category:continue
            cell=f'D{row}';label=cells.get(cell);target=hyperlinks.get(sheet,{}).get(cell)
            url=label if isinstance(label,str) and label.startswith(('http://','https://')) else target
            records.append(dict(bank=bank,currency_hint=currency,rate_type=category,url=url,
                cell=cell,sheet=sheet,workbook=str(Path(path).resolve()),display_value=label,
                hyperlink_target=target,status='registered' if url else 'missing_link'))
    return records


def bank_link(path, bank, currency, category, domains):
    book=read_xlsx(path,merge_anchors_only=True)
    targets=read_hyperlinks(path) if Path(path).exists() else {}
    cells=next(iter(book.values()));last=max(int(re.search(r'\d+',k)[0]) for k in cells)
    current_bank=current_currency=None;matches=[]
    for row in range(2,last+1):
        if cells.get(f'A{row}'):
            current_bank=cells[f'A{row}'].strip();current_currency=None
        current_currency=cells.get(f'B{row}') or current_currency
        if (bank_name(current_bank)==bank_name(bank) and current_currency==currency
                and cells.get(f'C{row}')==category):
            cell=f'D{row}';value=cells.get(cell)
            url=value if isinstance(value,str) and value.startswith(('http://','https://')) else targets.get(next(iter(book)),{}).get(cell)
            matches.append((cell,url))
    if len(matches)!=1:raise ValueError(f'{bank} {currency} {category} 链接缺失或不唯一，请检查利率链接表')
    cell,url=matches[0];parsed=urlsplit(url or '')
    if parsed.scheme!='https' or parsed.hostname not in domains or parsed.username or parsed.password:
        raise ValueError(f'{bank} {cell} 必须填写已登记的银行官方HTTPS网址')
    return dict(workbook=str(Path(path).resolve()),sheet=next(iter(book)),cell=cell,url=url)

"""Do not let a composed workflow go back to an older partial template."""
import re
from .xlsx_read import read_xlsx
from .board_plan import col,cell_number
from .weekly_history import date_value

def dated_columns(s,bank_col,current_col):
    rows=[int(a[len(col(bank_col)):]) for a,v in s.items() if re.fullmatch(col(bank_col)+r'\d+',a) and v in ['Bank','银行','日期']]
    if not rows:raise ValueError('Missing historical date header')
    r=min(rows);dates=set()
    for c in range(current_col,1000):
        v=cell_number(s.get(col(c)+str(r)))
        if isinstance(v,(int,float)) and 30000<v<80000:dates.add(date_value(v))
        elif isinstance(v,str) and re.fullmatch(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}',v):dates.add(date_value(v))
    return dates

def check_dates(previous,current):
    before=read_xlsx(previous,merge_anchors_only=True);after=read_xlsx(current,merge_anchors_only=True);result={}
    for name,bc,cc in [('SGD促销',1,3),('USD挂牌',2,4),('CNY挂牌',1,3),('USD促销',2,4),('CNY促销',1,3)]:
        old=dated_columns(before[name],bc,cc);new=dated_columns(after[name],bc,cc)
        missing=old-new
        if missing:raise ValueError('统一底稿丢失历史日期：'+name+' '+str(sorted(missing)))
        result[name]=dict(preserved=len(old),dates=sorted(new,reverse=True))
    return result

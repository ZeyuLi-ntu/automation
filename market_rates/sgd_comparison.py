"""Compare selected SGD banks with their most recent numeric historical quote."""
import re
from .board_plan import col,cell_number

def comparisons(sheet,merges):
    dc=next(re.match('[A-Z]+',a)[0] for a,v in sheet.items() if v=='当日最高报价变动')
    last=0
    for ch in dc:last=26*last+ord(ch)-64
    spans={}
    for address in merges:
        m=re.fullmatch(r'A(\d+):A(\d+)',address)
        if m:spans[int(m[1])]=int(m[2])
    out=[]
    for a,bank in sheet.items():
        if not re.fullmatch(r'A\d+',a) or bank not in ['UOB','Singapura Finance']:continue
        first=int(a[1:]);end=spans.get(first,first)
        def nums(c):
            return [v for r in range(first,end+1) for v in [cell_number(sheet.get(col(c)+str(r))) ] if isinstance(v,(int,float))]
        now=nums(3);previous=next((c for c in range(4,last) if nums(c)),None)
        expected=round(max(now)-max(nums(previous)),8) if now and previous else '无上期数据' if now else '-'
        out.append(dict(bank=bank,row=first,end=end,address=dc+str(first),previous_column=previous,expected=expected))
    return sorted(out,key=lambda x:x['row'])

def check_saved(path,values=None):
    from .xlsx_read import read_xlsx,merged_ranges
    values=values or read_xlsx(path,merge_anchors_only=True)
    sheet=values['SGD促销'];forms=read_xlsx(path,formulas=True,merge_anchors_only=True)['SGD促销']
    result=comparisons(sheet,merged_ranges(path)['SGD促销'])
    for x in result:
        actual=cell_number(sheet.get(x['address']));expected=x['expected']
        assert (abs(actual-expected)<1e-10 if isinstance(actual,(int,float)) and isinstance(expected,(int,float)) else actual==expected),(x,actual)
        assert str(forms.get(x['address'],'')).startswith('='),(x,'missing formula')
    return result

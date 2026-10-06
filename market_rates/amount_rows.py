"""Stable amount identities for historical labels and generated quote captions."""
import re
from decimal import Decimal

def amount_identity(label,bank=''):
    s=str(label or '').replace('，',',').replace('＜','<').replace('＞','>').replace('–','-').replace('—','-')
    parts=s.split('；');s=next((x for x in parts if re.search(r'(?:≥|≤|[<>])\s*[\d,]|\d[\d,]*(?:\.\d+)?\s*[kK]?\s*(?:-|以上|以下)',x)),s)
    nums=[Decimal(n.replace(',',''))*(1000 if k else 1) for n,k in re.findall(r'(\d[\d,]*(?:\.\d+)?)\s*([kK]?)',s)]
    if not nums:return None
    upper=lambda x:x+1 if x==int(x) and str(int(x)).endswith('999') else x
    if bank=='CIMB':return ('tier',nums[0])
    if len(nums)>1:return ('range',nums[0],upper(nums[1]))
    if re.search(r'<(?![=>])|≤|以下|Below|Up to|First',s,re.I):return ('range',None,upper(nums[0]))
    return ('range',nums[0],None)

def same_amount(a,b,bank='',candidates=()):
    def unit(label):
        m=re.search(r'\b(USD|SGD|CNY|CNH|AUD|NZD|EUR|GBP|CAD|HKD)\b',str(label))
        return ('CNY' if m[1]=='CNH' else m[1]) if m else 'CNY' if 'R$' in str(label) else 'USD' if 'URD' in str(label) else None
    ua,ub=unit(a),unit(b)
    if ua and ub and ua!=ub:return False
    x,y=amount_identity(a,bank),amount_identity(b,bank)
    if not x or not y:return False
    if x==y:return True
    if bank=='CIMB':return False
    # A legacy "Below 25k" heading means the corresponding upper-bound band;
    # use it only when the current candidate at that upper boundary is unique.
    if x[0]=='range' and y[0]=='range' and x[2] is not None and x[2]==y[2] and (x[1] is None or y[1] is None):
        ids={amount_identity(z,bank) for z in candidates if amount_identity(z,bank) and amount_identity(z,bank)[2]==x[2]}
        return len(ids)<=1
    return False

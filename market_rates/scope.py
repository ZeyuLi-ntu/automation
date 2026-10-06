"""Shared currency/type boundaries. Legacy callers remain explicitly SGD promo."""
import re

def bank_name(value):
    value=str(value or '').strip()
    aliases={'maybank':'Maybank','maribank':'MARI','mari':'MARI','trustbank':'TRUST','trust':'TRUST',
        'citibank':'CITI','hl bank':'HLB','posb':'POSB','dbs/posb':'DBS/POSB'}
    return aliases.get(value.casefold(),value)

def currency_code(value):
    code=value.strip().upper()
    code={'RMB':'CNY'}.get(code,code)
    if not re.fullmatch('[A-Z]{3}',code):raise ValueError('币种必须使用明确的三字母代码')
    return code

def scopes(config):return config.get('rate_scopes') or [{'currency':'SGD','rate_type':'promo'}]

def in_scope(row,config):
    return any(row['currency']==s['currency'] and row['rate_type']==s['rate_type'] for s in scopes(config))

def scope_id(currency,rate_type):
    if rate_type not in ['promo','board']:raise ValueError('未知利率类别')
    return currency_code(currency)+'/'+rate_type

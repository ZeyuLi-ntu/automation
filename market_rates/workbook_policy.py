"""User-confirmed presentation scope; does not change source or review state."""
from pathlib import Path
from decimal import Decimal
import re
from .common import load


def workbook_policy(config=None):
    return dict((config or {}).get('workbook_policy') or load(Path(__file__).resolve().parents[1]/'config/workbook-policy.json'))


def included_groups(groups, policy):
    deferred=set(policy.get('deferred_product_ids', []))
    return [g for g in groups if g['product_id'] not in deferred and bank_in_scope(g['bank'],policy)]

def bank_in_scope(bank,policy=None):
    from .scope import bank_name
    canonical=bank_name(bank)
    return canonical not in (policy or workbook_policy()).get('excluded_banks',[])


def currency_in_scope(currency,policy=None):
    from .scope import currency_code
    return currency_code(currency) not in (policy or workbook_policy()).get('excluded_currencies',[])


def presentation_currency(currency,policy=None):
    from .scope import currency_code
    code=currency_code(currency)
    return (policy or workbook_policy()).get('presentation_currency_map',{}).get(code,code)


def board_rate_usable(offer,policy=None):
    if offer['rate_basis']=='annual_nominal':return True
    # The user controls the display unit. Preserve the source basis as unknown;
    # this is not a claim that the bank printed an annual basis.
    return (offer['rate_type']=='board' and offer['rate_basis']=='unknown'
            and (policy or workbook_policy()).get('board_rate_unit')=='percent')


def promo_reference_allowed(offer, as_of, policy=None):
    """Display the latest collected publication even after its stated expiry.

    Call only on the current verified capture, never on historical workbook
    rows. Source collectors choose the latest announcement before extraction.
    Expiry remains unchanged; withdrawn and future offers are not references.
    """
    p=policy or workbook_policy()
    enabled=(p.get('promo_quote_date_policy')=='latest_published_reference'
             or offer['product_id'] in p.get('latest_published_promo_reference_products',[]))
    return bool(enabled and offer['rate_type']=='promo'
                and offer['availability']=='available' and offer['rate_pct'] is not None
                and (not offer.get('valid_from') or offer['valid_from']<=as_of)
                and offer.get('valid_to') and offer['valid_to']<as_of)

def quote_in_scope(offer,policy=None):
    p=policy or workbook_policy()
    if offer['bank']=='Maybank' and offer['rate_type']=='board' and offer['currency']!='SGD':
        return offer['product_id'] in p.get('maybank_fx_board_products',[offer['product_id']])
    if offer['bank']=='HSBC':
        key='hsbc_board_audiences' if offer['rate_type']=='board' else 'hsbc_usd_promo_audiences' if offer['currency']=='USD' else None
        if key and key in p:return offer['audience'] in p[key]
    return True


def daily_change_cells(cells):
    """Recognize the labeled comparison column, including already-shifted formulas."""
    cols={re.match(r'[A-Z]+',a)[0] for a,v in cells.items() if v=='当日最高报价变动'}
    return [a for a,v in cells.items() if isinstance(v,str) and v.startswith('=') and
            (re.match(r'[A-Z]+',a)[0] in cols or re.fullmatch(r'=\$?C\$?(\d+)-\$?D\$?\1',v))]


def daily_change_formula(row):
    # INDEX selects fixed physical date columns even after another C insertion.
    now=f'INDEX({row}:{row},1,3)';previous=f'INDEX({row}:{row},1,4)'
    return f'=IF(COUNT({now},{previous})=2,{now}-{previous},"-")'


def bank_blocks(blocks):
    """One bank block per tenor; Personal priority also determines bank rank."""
    by_bank={}
    for b in blocks:by_bank.setdefault(b['bank'],[]).append(b)
    ranked=[]
    for index,products in enumerate(by_bank.values()):
        candidates=[(b,r) for b in products for r in b.get('group',{}).get('details',[])]
        personal=[pair for pair in candidates if pair[1]['audience']=='personal']
        if candidates:
            winner,quote=max(personal or candidates,key=lambda pair:Decimal(pair[1]['rate_pct']))
            rank=Decimal(quote['rate_pct'])/100
            products=[winner]+[b for b in products if b is not winner]
        else:rank=max(Decimal(str(b['rank_rate'])) for b in products)
        prior=min(b.get('prior_index',index) for b in products)
        ranked.append((rank,prior,index,products))
    ranked.sort(key=lambda item:(-item[0],item[1],item[2]))
    return [dict(b,bank_rank_rate=str(rank)) for rank,_,_,products in ranked for b in products]

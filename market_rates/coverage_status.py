"""Non-numeric source status; never relaxes model agreement or supplies rates."""
from pathlib import Path
from .common import load
from .table_validation import sha
from .workbook_policy import bank_in_scope

NOTES={
 'DBS':'本次公开页面未取得 SGD 定存促销报价；外币促销和 SGD 挂牌未混入。',
 'POSB':'公开来源为挂牌利率页；本次未取得 SGD 定存促销报价。',
 'MARI':'官网未展示可供两路提取的定存利率；App 内报价待人工提供。',
 'TRUST':'公开 Savings Pots 为储蓄类产品；未取得符合范围的 SGD 定存促销报价。',
}

def public_inventory(folder):
    folder=Path(folder);r=load(folder/'status.json')
    return [dict(bank=b,numeric_insertion=False,status='no_verified_public_quote',reason=note,
       checked_at=r['captured_at'],urls=[p['url'] for p in r['pages'] if p['bank']==b],
       evidence=str((folder/'evidence/index.html').resolve()),status_sha256=sha(folder/'status.json'))
       for b,note in NOTES.items() if bank_in_scope(b)]

def failed_collection(bank,folder):
    folder=Path(folder);r=load(folder/'run.json');cfg=load(folder/'config.snapshot.json')
    return dict(bank=bank,numeric_insertion=False,status='collection_failed',
        reason='官网连接失败，尚未完成本地文字/视觉双路核验；本期留空值“-”。',
        checked_at=r['as_of'],urls=[u for s in cfg['sources'] for u in s['urls']],
        errors=r.get('errors',[]),run_path=str(folder.resolve()),run_sha256=sha(folder/'run.json'))

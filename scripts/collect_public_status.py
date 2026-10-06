"""Capture official public pages without inventing promotional quote rows."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from market_rates.capture import capture_sources
from market_rates.common import save
from market_rates.pipeline import evidence_index
from market_rates.workbook_policy import bank_in_scope

SOURCES={
 'DBS':['https://www.dbs.com.sg/personal/deposits/fixed-deposits/fixed-deposit'],
 'POSB':['https://www.posb.com.sg/personal/rates-online/fixed-deposit-rate-singapore-dollar.page'],
 'MARI':['https://www.maribank.sg/product/mari-fixed-deposit','https://www.maribank.sg/promo'],
 'TRUST':['https://trustbank.sg/savings-pots/'],
}

def collect(out):
    from urllib.parse import urlsplit
    out=Path(out)
    if out.exists():raise ValueError('请选择新证据目录')
    cfg=dict(sources=[dict(id='public-'+bank,bank=bank,enabled=True,urls=urls,
      domains=sorted({urlsplit(u).hostname for u in urls}),max_depth=0,max_pages=len(urls),product_ids=[],settle_ms=1500)
      for bank,urls in SOURCES.items() if bank_in_scope(bank)])
    pages,errors=capture_sources(cfg,out/'evidence');evidence_index(pages,out/'evidence')
    save(out/'status.json',dict(captured_at=datetime.now(timezone.utc).isoformat(),pages=pages,errors=errors,
      note='只登记官方页面证据；未生成报价，未宣称已覆盖 App、登录后或非公开优惠。'))
    print({'pages':len(pages),'errors':errors})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();collect(a.out)

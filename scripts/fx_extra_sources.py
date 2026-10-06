"""Resolve official current FX terms without a cloud model."""
from pathlib import Path
import re,hashlib,pymupdf
from playwright.sync_api import sync_playwright
from market_rates.common import load,save
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS,PAGE_SETTLE_MS
ROOT=Path('runs/fx-promo-discovery-20260928-a/attachments')
with sync_playwright() as pw:
    b=pw.chromium.launch(headless=True,args=['--disable-http2']);ctx=b.new_context();p=ctx.new_page()
    url=load(Path('runs/fx-promo-discovery-20260928-a/CITI-D17/source.json'))['url']
    p.goto(url,timeout=PAGE_LOAD_TIMEOUT_MS,wait_until='domcontentloaded');p.wait_for_timeout(PAGE_SETTLE_MS)
    links=p.locator('a').evaluate_all('els=>els.map(e=>({url:e.href,text:e.parentElement.innerText}))')
    selected=[x for x in links if re.search(r'New-to-Bank New Funds|Citigold Time Deposit Promotion Terms',x['text'])]
    selected=list({x['url'].replace('http:','https:').split('?')[0].rstrip('/'):x for x in selected}.values())
    selected.append(dict(url='https://www.dbs.com.sg/iwov-resources/media/pdf/others/retail-terms-and-conditions-usd-fd-promotion-aug-2026-1.pdf',text='DBS USD bonus'))
    for x in selected:
        bank='DBS' if 'dbs.com' in x['url'] else 'CITI';out=ROOT/(bank+'-'+hashlib.sha256(x['url'].encode()).hexdigest()[:7]);out.mkdir(exist_ok=True)
        r=ctx.request.get(x['url'].replace('http:','https:'),timeout=PAGE_LOAD_TIMEOUT_MS)
        if r.status!=200:raise ValueError(r.status)
        raw=r.body();(out/'source.pdf').write_bytes(raw);doc=pymupdf.open(stream=raw,filetype='pdf');text='\n'.join(pg.get_text() for pg in doc)
        save(out/'source.json',dict(bank=bank,url=r.url,kind='pdf',text=text,context=x['text']));print(bank,r.url,text[:220],flush=True)
    p.goto('https://www.bankofchina.com/sg/bocinfo/bi3/',timeout=PAGE_LOAD_TIMEOUT_MS,wait_until='domcontentloaded');p.wait_for_timeout(PAGE_SETTLE_MS)
    matches=p.locator('a').evaluate_all('els=>els.map(e=>({url:e.href,text:e.innerText})).filter(e=>/deposit|promotion/i.test(e.text))')
    save(ROOT/'boc-english-notices.json',matches);print('BOC',matches[:15],flush=True);b.close()

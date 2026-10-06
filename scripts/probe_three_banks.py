"""Read-only page discovery for the three-bank pilot; never logs into a bank."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from market_rates.common import save
from market_rates.xlsx_read import read_xlsx

p = argparse.ArgumentParser()
p.add_argument('--bank', choices=['HLF', 'CIMB', 'RHB','OCBC','HLB','SBI','UOB','ICBC','BOC'], required=True)
p.add_argument('--out', required=True)
p.add_argument('--url')
p.add_argument('--route',action='store_true')
a = p.parse_args()
cells = next(iter(read_xlsx('../利率链接.xlsx').values()))
url = a.url or cells[{'HLF': 'D32', 'CIMB': 'D14', 'RHB': 'D57','OCBC':'D52','HLB':'D27','SBI':'D72','UOB':'D77','ICBC':'D42','BOC':'D9'}[a.bank]].split('?')[0]
out = Path(a.out)
out.mkdir(parents=True, exist_ok=False)
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    page = b.new_page(viewport={'width': 1440, 'height': 1100}, locale='en-SG')
    if a.route:
        from market_rates.capture import allowed
        from urllib.parse import urlsplit
        def guard(route):
            if route.request.is_navigation_request() and not allowed(route.request.url,[urlsplit(url).hostname]):
                print('Blocked navigation',route.request.url,flush=True);route.abort()
            else:route.continue_()
        page.context.route('**/*',guard)
    try:
        response = page.goto(url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT_MS)
        page.wait_for_timeout(PAGE_SETTLE_MS)
        (out/'page.html').write_text(page.content(), encoding='utf8')
        (out/'body.txt').write_text(page.locator('body').inner_text(), encoding='utf8')
        page.screenshot(path=str(out/'page.png'), full_page=True, timeout=SCREENSHOT_TIMEOUT_MS)
        info = page.locator('body').evaluate(r'''e => ({
          tables: [...e.querySelectorAll('table')].map((t,i)=>({index:i,text:t.innerText,parents:[t.parentElement,t.parentElement?.parentElement,t.parentElement?.parentElement?.parentElement,t.parentElement?.parentElement?.parentElement?.parentElement].filter(Boolean).map(p=>({tag:p.tagName,id:p.id,cls:p.className}))})),
          sections:[...e.querySelectorAll('section,main,[id]')].map(x=>({tag:x.tagName,id:x.id,cls:x.className,title:(x.innerText||'').slice(0,80)})),
          links:[...e.querySelectorAll('a[href]')].map(x=>({text:x.innerText,url:x.href})).filter(x=>/deposit|fixed|terms|\.pdf|click here|存款|促销|利率/i.test(x.text+' '+x.url))
        })''')
        info.update(url=page.url,status=response.status if response else None)
        save(out/'inspection.json', info)
        print(json.dumps(info,ensure_ascii=False))
    finally:
        b.close()

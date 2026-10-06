"""Bounded fresh link discovery, starting from the user's link workbook."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import urlsplit,urlunsplit
from .common import save
from .xlsx_read import read_xlsx
from .capture import allowed

def discover(links,out):
    from playwright.sync_api import sync_playwright
    sheet,cells=next(iter(read_xlsx(links).items()))
    domains={'RHB':['rhbgroup.com.sg','www.rhbgroup.com.sg'],'CIMB':['www.cimb.com.sg','www.cimbpreferred.com.sg']}
    def clean(cell):
        u=urlsplit(cells[cell]);return urlunsplit((u.scheme,u.netloc,u.path,'',''))
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    def unique(info,pattern):
        urls=list(dict.fromkeys(x['url'] for x in info['links'] if re.search(pattern,x['url'],re.I)))
        if len(urls)!=1:raise ValueError('Product-link discovery is absent or ambiguous: '+pattern)
        return urls[0]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},locale='en-SG')
        def read(bank,label,url):
            if not allowed(url,domains[bank]):raise ValueError('Discovery left registered bank domain')
            page=context.new_page()
            def guard(route):
                if route.request.is_navigation_request() and not allowed(route.request.url,domains[bank]):route.abort()
                else:route.continue_()
            page.route('**/*',guard)
            try:
                response=page.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                page.wait_for_timeout(PAGE_SETTLE_MS)
                if not response or response.status>=400 or not allowed(page.url,domains[bank]):raise ValueError('Official discovery page unavailable')
                page.locator('body').wait_for(state='attached', timeout=CONTENT_TIMEOUT_MS)
                anchors=page.locator('a[href]').evaluate_all('els=>els.map(x=>({text:x.innerText,url:x.href}))')
                data=dict(requested_url=url,final_url=page.url,captured_at=datetime.now(timezone.utc).isoformat(),links=anchors)
                folder=out/label;folder.mkdir()
                save(folder/'inspection.json',data)
                (folder/'page.html').write_text(page.content(),encoding='utf8')
                (folder/'body.txt').write_text(page.locator('body').inner_text(),encoding='utf8')
                return data
            finally:page.close()
        try:
            read('RHB','RHB',clean('D57'))
            rates=read('CIMB','CIMB',clean('D14'))
            regular=read('CIMB','CIMB-product',unique(rates,r'/cimb-sgd-fixed-deposit-account\.html$'))
            read('CIMB','CIMB-wwfd',unique(rates,r'/cimb-why-wait-fixed-deposit-i-account\.html$'))
            read('CIMB','CIMB-preferred',unique(regular,r'www\.cimbpreferred\.com\.sg/.*/preferred-acquisition\.html$'))
            save(out/'manifest.json',dict(input_workbook=str(Path(links).resolve()),sheet=sheet,cells=['D57','D14'],
                scope='Rate/product/campaign links only; no login, forms, or application submissions'))
        finally:context.close();browser.close()
    return out

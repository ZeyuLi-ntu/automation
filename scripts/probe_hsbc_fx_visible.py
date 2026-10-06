from pathlib import Path
from playwright.sync_api import sync_playwright
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS
import re,json

out=Path('runs/hsbc-fx-visible-20260929');out.mkdir(exist_ok=True)
with sync_playwright() as pw:
    b=pw.chromium.launch(headless=True,args=['--disable-http2']);p=b.new_page(viewport={'width':1700,'height':1900})
    p.goto('https://www.hsbc.com.sg/accounts/products/foreign-currency-time-deposit/',wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS);p.wait_for_timeout(5000)
    (out/'page.html').write_text(p.content(),encoding='utf8');(out/'page.txt').write_text(p.locator('body').inner_text(),encoding='utf8')
    heads=p.get_by_text(re.compile(r'^For Personal Banking customers:')).all()
    data={'heads':[{'visible':h.is_visible(),'html':h.evaluate('e=>e.parentElement.outerHTML')} for h in heads],
          'tables':[{'visible':t.is_visible(),'text':t.inner_text(),'html':t.evaluate('e=>e.outerHTML')} for t in p.locator('table').all()]}
    (out/'diagnostics.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(data,ensure_ascii=False)[:14000]);b.close()

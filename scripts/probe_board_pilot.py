"""Archive candidate official board-rate pages locally before choosing a pilot."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import asyncio
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright
from market_rates.xlsx_read import read_xlsx
from market_rates.common import save

async def main():
    cells=next(iter(read_xlsx('../利率链接.xlsx',merge_anchors_only=True).values()))
    out=Path('runs/board-discovery-20260927');out.mkdir(exist_ok=True)
    choices={'BEA-SGD':'D5','BEA-USD':'D3','HLB-SGD':'D28','HLB-USD':'D26','SBI-both':'D71'}
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True);sem=asyncio.Semaphore(2)
        async def probe(key,cell):
            async with sem:
                url=cells[cell];page=await browser.new_page(viewport={'width':1440,'height':1100},locale='en-SG')
                try:
                    response=await page.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                    await page.wait_for_timeout(PAGE_SETTLE_MS)
                    if not response or response.status>=400:raise ValueError('HTTP '+str(response.status if response else None))
                    data=dict(url=url,cell=cell,final_url=page.url,status=response.status,
                        tables=await page.locator('table').evaluate_all('els=>els.map(e=>({id:e.id,cls:e.className,text:e.innerText,html:e.outerHTML,parent:e.parentElement.outerHTML.slice(0,25000)}))'),
                        links=await page.locator('a[href]').evaluate_all('els=>els.map(e=>({text:e.innerText,url:e.href})).filter(e=>/rates|deposit|pdf/i.test(e.text+e.url))'))
                    save(out/(key+'.json'),data)
                    (out/(key+'.html')).write_text(await page.content(),encoding='utf8')
                    (out/(key+'.txt')).write_text(await page.locator('body').inner_text(),encoding='utf8')
                    print(key,{'tables':len(data['tables']),'status':response.status,'sizes':[len(t['text']) for t in data['tables']]},flush=True)
                except Exception as exc:save(out/(key+'-error.json'),dict(url=url,error=str(exc)));print(key,str(exc)[:180],flush=True)
                finally:await page.close()
        try:await asyncio.gather(*(probe(k,c) for k,c in choices.items()))
        finally:await browser.close()

if __name__=='__main__':asyncio.run(main())

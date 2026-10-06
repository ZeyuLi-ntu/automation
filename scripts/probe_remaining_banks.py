"""Read-only discovery of remaining official SGD deposit sources."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from playwright.async_api import async_playwright
from market_rates.common import save,load
from market_rates.xlsx_read import read_xlsx
from market_rates.workbook_policy import bank_in_scope
from market_rates.link_registry import bank_link

async def main():
    cli=argparse.ArgumentParser();cli.add_argument('--extra');cli.add_argument('--out',default='runs/remaining-discovery-20260927');args=cli.parse_args()
    cells=next(iter(read_xlsx('../利率链接.xlsx',merge_anchors_only=True).values()))
    urls={k:cells[c] for k,c in {'BEA':'D4','CITI':'D17','HSBC':'D37','SingFinance':'D62','Singapura Finance':'D81'}.items()}
    urls.update({'Maybank':bank_link('../利率链接.xlsx','maybank','SGD','促销',['www.maybank2u.com.sg'])['url'],
      'DBS':'https://www.dbs.com.sg/personal/deposits/fixed-deposits/fixed-deposit',
      'MariBank':'https://www.maribank.sg/product/mari-fixed-deposit','Trust':'https://trustbank.sg/'})
    if args.extra:urls=load(args.extra)
    urls={bank:url for bank,url in urls.items() if bank_in_scope(bank)}
    out=Path(args.out);out.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=['--disable-http2'])
        sem=asyncio.Semaphore(3)
        async def read(bank,url):
            async with sem:
                p=urlsplit(url);url=urlunsplit((p.scheme,p.netloc,p.path,'',''))
                page=await browser.new_page(viewport={'width':1440,'height':1100},locale='en-SG')
                try:
                    if urlsplit(url).path.lower().endswith('.pdf'):
                        import pymupdf
                        response=await page.request.get(url,timeout=PAGE_LOAD_TIMEOUT_MS)
                        data=await response.body()
                        if response.status!=200 or not data.startswith(b'%PDF'):raise ValueError('PDF unavailable')
                        (out/(bank+'.pdf')).write_bytes(data)
                        doc=pymupdf.open(stream=data,filetype='pdf')
                        (out/(bank+'.txt')).write_text('\n'.join(p.get_text() for p in doc),encoding='utf8')
                        print(bank,'PDF',len(doc),flush=True);return
                    response=await page.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                    await page.wait_for_timeout(PAGE_SETTLE_MS)
                    info=dict(bank=bank,url=url,final_url=page.url,status=response.status if response else None,at=datetime.now(timezone.utc).isoformat())
                    info['links']=await page.locator('a[href]').evaluate_all('es=>es.map(e=>({text:e.innerText,url:e.href}))')
                    info['tables']=await page.locator('table').evaluate_all('es=>es.map(e=>({id:e.id,cls:e.className,text:e.innerText}))')
                    info['images']=await page.locator('img').evaluate_all('es=>es.map(e=>({src:e.src,alt:e.alt}))')
                    save(out/(bank+'.json'),info)
                    (out/(bank+'.txt')).write_text(await page.locator('body').inner_text(),encoding='utf8')
                    (out/(bank+'.html')).write_text(await page.content(),encoding='utf8')
                    await page.screenshot(path=str(out/(bank+'.png')),full_page=True, timeout=SCREENSHOT_TIMEOUT_MS)
                    print(bank,info['status'],len(info['tables']),'tables',flush=True)
                except Exception as e:save(out/(bank+'-error.json'),dict(url=url,error=str(e)));print(bank,str(e),flush=True)
                finally:await page.close()
        try:await asyncio.gather(*(read(b,u) for b,u in urls.items()))
        finally:await browser.close()

if __name__=='__main__':asyncio.run(main())

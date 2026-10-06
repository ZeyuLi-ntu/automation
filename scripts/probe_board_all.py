"""Read every registered board source once; isolate unavailable bank sources."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse,asyncio,hashlib,re
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit
from playwright.async_api import async_playwright
from market_rates.common import save
from market_rates.link_registry import entries
from market_rates.workbook_policy import bank_in_scope
from scripts.capture_board_batch import GRID
from scripts.capture_board_wave import PHYSICAL

async def wait_for_dynamic_board(page,bank):
    if bank in ['DBS','POSB','OCBC']:
        # DOM ready / HTTP 200 can still be a loading placeholder or an invalid
        # route. Wait for a visible table containing actual numeric rate cells.
        await page.wait_for_function("""() => [...document.querySelectorAll('table')].some(t =>
            t.getBoundingClientRect().width > 0 && [...t.querySelectorAll('td')].some(c =>
            /^\\s*\\d+\\.\\d+%?\\s*$/.test(c.innerText)))""",timeout=CONTENT_TIMEOUT_MS)

async def probe(out,banks=None,rate_type='board'):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    records=[r for r in entries('../利率链接.xlsx') if r['rate_type']==rate_type and bank_in_scope(r['bank'])]
    if banks:records=[r for r in records if r['bank'] in banks]
    save(out/'link-snapshot.json',records);sources={}
    for r in records:
        if r['url']:sources.setdefault(r['url'],[]).append(r)
    results=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=['--disable-http2']);sem=asyncio.Semaphore(3)
        async def one(url,rs):
            async with sem:
                key=rs[0]['bank']+'-'+rs[0]['cell'];folder=out/key;folder.mkdir()
                p=await browser.new_page(viewport={'width':1440,'height':1600},locale='en-SG',device_scale_factor=1.5)
                item=dict(id=key,bank=rs[0]['bank'],url=url,registry=rs,captured_at=datetime.now(timezone.utc).isoformat())
                try:
                    if urlsplit(url).path.lower().endswith('.pdf'):
                        resp=await p.request.get(url,timeout=PAGE_LOAD_TIMEOUT_MS)
                        if resp.status!=200:raise ValueError('HTTP '+str(resp.status))
                        content=await resp.body();(folder/'source.pdf').write_bytes(content)
                        import fitz
                        doc=fitz.open(stream=content,filetype='pdf');texts=[]
                        for i,page in enumerate(doc):
                            texts.append(page.get_text());page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(str(folder/f'page-{i+1}.png'))
                        item.update(kind='pdf',text='\n'.join(texts),pages=len(doc),tables=[])
                    else:
                        resp=await p.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                        if not resp or resp.status>=400:raise ValueError('HTTP '+str(resp.status if resp else None))
                        if item['bank']=='BEA' and rate_type=='board':
                            # The legacy URL redirects to a JavaScript form; DOM ready
                            # can be an empty app shell, not a missing bank rate page.
                            await p.locator('table').first.wait_for(state='visible',timeout=CONTENT_TIMEOUT_MS)
                        if item['bank'] in ['DBS','POSB','OCBC'] and rate_type=='board':
                            try:await wait_for_dynamic_board(p,item['bank'])
                            except Exception as e:
                                item.update(content_not_ready=True,content_error='未等到可见利率表；不能视作无报价或完成采集')
                        await p.wait_for_timeout(PAGE_SETTLE_MS)
                        item.update(kind='html',final_url=p.url,text=await p.locator('body').inner_text(),tables=[],
                            links=await p.locator('a[href]').evaluate_all('xs=>xs.map(x=>({text:x.innerText.trim(),url:x.href})).filter(x=>/rate|deposit|pdf|利率/i.test(x.text+x.url))'))
                        (folder/'source.html').write_text(await p.content(),encoding='utf8')
                        if item['bank']=='HSBC':
                            for link in item['links']:
                                if 'Foreign Currency Time Deposit rates' in link['text'] and 'Personal Banking' in link['text'] and link['url'].split('?')[0].endswith('.pdf'):
                                    attachment=await p.request.get(link['url'],timeout=PAGE_LOAD_TIMEOUT_MS)
                                    if attachment.status!=200:raise ValueError('Linked HSBC PDF unavailable')
                                    name='fcy-time-deposits-'+('pb' if 'Personal Banking' in link['text'] else 'pr' if 'Premier' in link['text'] else 'unknown')+'.pdf'
                                    (folder/name).write_bytes(await attachment.body())
                        for i,t in enumerate(await p.locator('table').all()):
                            visible=await t.is_visible();grid=await t.evaluate(GRID)
                            if grid and re.search(r'Japanese Yen|\bJPY\b',str(grid[0]),re.I):continue
                            row=dict(index=i,visible=visible,grid=grid,rows=await t.evaluate(PHYSICAL),text=await t.inner_text())
                            if visible and any(grid):
                                try:
                                    await t.screenshot(path=str(folder/f'table-{i}.png'),animations='disabled',timeout=SCREENSHOT_TIMEOUT_MS)
                                    row['image']=f'table-{i}.png'
                                except Exception as e:row['image_error']=str(e)[:200]
                            item['tables'].append(row)
                        await p.screenshot(path=str(folder/'page.png'),full_page=True,animations='disabled',timeout=SCREENSHOT_TIMEOUT_MS)
                    item['status']='incomplete_capture' if item.get('content_not_ready') else 'captured' if item.get('text','').strip() else 'empty_capture'
                except Exception as e:item.update(status='unavailable',error=str(e)[:600])
                finally:
                    if item.get('text'):(folder/'source.txt').write_text(item['text'],encoding='utf8')
                    item['hashes']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.iterdir() if f.is_file()}
                    save(folder/'source.json',item);results.append(item)
                    save(out/'status.json',[{k:v for k,v in x.items() if k not in ['text','tables','links','hashes']} for x in results])
                    print(key,item['status'],len(item.get('tables',[])),item.get('error','')[:80],flush=True);await p.close()
        try:await asyncio.gather(*(one(u,rs) for u,rs in sources.items()))
        finally:await browser.close()

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);a.add_argument('--banks');a.add_argument('--rate-type',choices=['board','promo'],default='board');x=a.parse_args();asyncio.run(probe(x.out,x.banks.split(',') if x.banks else None,x.rate_type))

"""Read-only investigation of missing board sources; never publishes rates."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse, asyncio, hashlib, re
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright
from market_rates.common import load, save
from market_rates.link_registry import entries
from scripts.capture_board_wave import PHYSICAL


async def probe(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    registry = entries('../利率链接.xlsx')
    selected = {'D21', 'D51', 'D41', 'D71', 'D76', 'D56', 'D33', 'D68', 'D53', 'D18', 'D26'}
    sources = [r for r in registry if r['cell'] in selected and r['url']]
    save(out / 'link-snapshot.json', sources)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--disable-http2'])
        sem = asyncio.Semaphore(3)
        async def one(src):
            async with sem:
                key = src['bank'] + '-' + src['cell']; folder = out / key; folder.mkdir()
                p = await browser.new_page(viewport={'width': 1600, 'height': 1200}, locale='en-SG')
                item = dict(id=key, bank=src['bank'], registry=src, url=src['url'],
                            captured_at=datetime.now(timezone.utc).isoformat(), views=[])
                responses=[]
                p.on('response', lambda r: responses.append({'url': r.url, 'status': r.status}) if r.request.resource_type in ['xhr','fetch','document'] else None)
                async def snapshot(label):
                    text = await p.locator('body').inner_text()
                    tables=[]
                    for i,t in enumerate(await p.locator('table').all()):
                        if await t.is_visible():
                            rows=await t.evaluate(PHYSICAL)
                            # Avoid nested navigation/layout tables duplicating all page data.
                            if rows and len(str(rows)) < 30000 and not re.search(r'\bJPY\b|Japanese Yen',str(rows[0]),re.I): tables.append(dict(index=i,rows=rows))
                    (folder/(label+'.txt')).write_text(text,encoding='utf8')
                    (folder/(label+'.html')).write_text(await p.content(),encoding='utf8')
                    await p.screenshot(path=str(folder/(label+'.png')), full_page=True, timeout=SCREENSHOT_TIMEOUT_MS)
                    item['views'].append(dict(label=label,url=p.url,text=text,tables=tables,
                        links=await p.locator('a[href]').evaluate_all('xs=>xs.map(x=>({text:x.innerText.trim(),url:x.href})).filter(x=>/deposit|rates|利率/i.test(x.text+x.url))'),
                        frames=[f.url for f in p.frames],selects=await p.locator('select').evaluate_all('xs=>xs.map(x=>({name:x.name,id:x.id,options:[...x.options].map(o=>({text:o.text,value:o.value}))}))')))
                try:
                    if src['url'].split('?')[0].lower().endswith('.pdf'):
                        r=await p.request.get(src['url'],timeout=PAGE_LOAD_TIMEOUT_MS)
                        if not r.ok: raise ValueError('HTTP '+str(r.status))
                        blob=await r.body();(folder/'source.pdf').write_bytes(blob)
                        import pymupdf
                        with pymupdf.open(stream=blob,filetype='pdf') as doc:
                            item['pdf_pages']=[dict(page=i+1,text=pg.get_text(),tables=[t.extract() for t in pg.find_tables().tables]) for i,pg in enumerate(doc)]
                        item['status']='pdf_captured'
                    else:
                        await p.goto(src['url'],wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                        if src['bank']=='OCBC' and src['cell']=='D51':
                            try: await p.wait_for_function("!document.body.innerText.includes('Loading...')",timeout=CONTENT_TIMEOUT_MS)
                            except Exception: pass
                        else: await p.wait_for_timeout(PAGE_SETTLE_MS)
                        await snapshot('initial')
                        if src['bank']=='ICBC':
                            for label in ['RMB Fixed Deposit','USD Fixed Deposit']:
                                await p.get_by_text(label,exact=True).filter(visible=True).first.click(timeout=CONTENT_TIMEOUT_MS)
                                await p.wait_for_timeout(PAGE_SETTLE_MS);await snapshot('cny' if label.startswith('RMB') else 'usd')
                        elif src['bank']=='SBI':
                            await p.get_by_text('Foreign Currencies',exact=True).filter(visible=True).first.click(timeout=CONTENT_TIMEOUT_MS)
                            await p.wait_for_timeout(PAGE_SETTLE_MS);await snapshot('fx')
                        elif src['bank']=='CITI':
                            await p.get_by_text('Click here to view the rates',exact=True).click(timeout=CONTENT_TIMEOUT_MS)
                            await snapshot('board-modal')
                        elif src['bank']=='DBS' and 'invalid' in item['views'][0]['text']:
                            footer=next((l['url'] for l in item['views'][0]['links'] if '/i-bank/rates-online/default.page' in l['url']),None)
                            if footer:
                                await p.goto(footer,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                                await p.get_by_text('Foreign Currency Fixed Deposits',exact=True).filter(visible=True).first.click(timeout=CONTENT_TIMEOUT_MS)
                                await p.wait_for_timeout(PAGE_SETTLE_MS);await snapshot('official-menu')
                        item['status']='inspected'
                    item['network']=responses
                except Exception as e: item.update(status='error',error=str(e)[:700])
                finally:
                    item['hashes']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.iterdir() if f.is_file()}
                    save(folder/'source.json',item)
                    print(key,item['status'],[(v['label'],len(v['tables'])) for v in item['views']],item.get('error','')[:150],flush=True)
                    await p.close()
        try: await asyncio.gather(*(one(s) for s in sources))
        finally: await browser.close()


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True)
    asyncio.run(probe(a.parse_args().out))

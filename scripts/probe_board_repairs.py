"""Inspect the user-identified live sources, including SPA routes and PDF links."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse,hashlib,re
from pathlib import Path
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright
from market_rates.common import save
from market_rates.link_registry import entries
from scripts.capture_board_wave import PHYSICAL,shot

def probe(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    registry=entries('../利率链接.xlsx')
    sources=[(r['bank']+'-'+r['cell'],r['bank'],r['url']) for r in registry if r['cell'] in ['D3','D5','D36','D38','D46','D66','D12']]
    sources += [('BEA-SGD-current','BEA','https://www.hkbea.com.sg/sg-form/?formId=RATE&rateType=fdr#/forms/MISC'),('BEA-FX-current','BEA','https://www.hkbea.com.sg/sg-form/?formId=RATE&rateType=fcfdr#/forms/MISC')]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--disable-http2'])
        context=browser.new_context(viewport={'width':1440,'height':1600},device_scale_factor=2,locale='en-SG')
        for key,bank,url in sources:
            folder=out/key;folder.mkdir();page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            item=dict(id=key,bank=bank,url=url,captured_at=datetime.now(timezone.utc).isoformat())
            try:
                response=page.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                if not response or response.status>=400:raise ValueError('HTTP '+str(response.status if response else None))
                try:page.locator('table').first.wait_for(state='visible',timeout=CONTENT_TIMEOUT_MS)
                except Exception:pass
                page.wait_for_timeout(PAGE_SETTLE_MS)
                item.update(final_url=page.url,text=page.locator('body').inner_text(),tables=[],links=page.locator('a[href]').evaluate_all('xs=>xs.map(x=>({text:x.innerText.trim(),url:x.href})).filter(x=>/rate|deposit|pdf|利率/i.test(x.text+x.url))'))
                (folder/'source.html').write_text(page.content(),encoding='utf8')
                (folder/'source.txt').write_text(item['text'],encoding='utf8')
                for i,table in enumerate(page.locator('table').all()):
                    if not table.is_visible():continue
                    rows=table.evaluate(PHYSICAL)
                    item['tables'].append(dict(index=i,rows=rows,box=table.bounding_box(),text=table.inner_text()))
                if key=='HSBC-D36':
                    links=[x for x in item['links'] if 'Foreign Currency Time Deposit rates' in x['text'] and 'Personal Banking' in x['text'] and x['url'].split('?')[0].endswith('.pdf')]
                    for link in links:
                        data=context.request.get(link['url'],timeout=PAGE_LOAD_TIMEOUT_MS)
                        if data.status!=200:raise ValueError('PDF unavailable')
                        name='fcy-time-deposits-'+('pb' if 'Personal Banking' in link['text'] else 'pr' if 'Premier' in link['text'] else 'unknown')+'.pdf';(folder/name).write_bytes(data.body())
                if bank=='BEA':page.screenshot(path=str(folder/'page.png'),full_page=True,animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS)
                item['status']='captured' if item['tables'] or len(item['text'])>200 else 'empty_capture'
                print(key,item['status'],page.url,'tables',len(item['tables']),'text',len(item['text']),flush=True)
            except Exception as e:item.update(status='failed',error=str(e));print(key,'ERROR',str(e)[:200],flush=True)
            finally:
                item['page_errors']=errors;save(folder/'source.json',item);page.close()
        browser.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);probe(p.parse_args().out)

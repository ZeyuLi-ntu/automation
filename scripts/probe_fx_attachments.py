"""Discover current BOC notice and archive linked official FX promotion terms."""
from pathlib import Path
import re,hashlib
import pymupdf
from playwright.sync_api import sync_playwright
from market_rates.common import load,save
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS,PAGE_SETTLE_MS
from scripts.capture_board_wave import PHYSICAL

def main():
    root=Path('runs/fx-promo-discovery-20260928-a');out=root/'attachments';out.mkdir(exist_ok=True)
    urls=[('DBS','https://www.dbs.com.sg/personal/promotion/usdfd-a')]
    for bank,key,pattern in [('CIMB','CIMB-D13','tnc-fcfd'),('CITI','CITI-D16','fcy-fxtd|aia-onshore'),('HSBC','HSBC-D35','aud-gbp-time|usd-time'),('RHB','RHB-D55','Governing%20FCY'),('SCB','SCB-D65','usd.*(?:tnc|promotion)|promotion.*usd')]:
        for link in load(root/key/'source.json').get('links',[]):
            if re.search(pattern,link['url'],re.I):urls.append((bank,link['url']))
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True,args=['--disable-http2']);c=b.new_context(viewport={'width':1600,'height':1600},device_scale_factor=1.5)
        p=c.new_page();p.goto(load(root/'BOC-D7/source.json')['url'],wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS);p.wait_for_timeout(PAGE_SETTLE_MS)
        candidates=p.locator('a[href]').evaluate_all("xs=>xs.map(x=>({text:x.innerText.trim(),url:x.href})).filter(x=>/^个人定期存款促销利率\\(\\d{8}\\)$/.test(x.text))")
        latest=max(candidates,key=lambda x:x['text']);urls.append(('BOC',latest['url']));p.close()
        seen=set()
        for bank,url in urls:
            if url in seen:continue
            seen.add(url);key=bank+'-'+hashlib.sha256(url.encode()).hexdigest()[:7];folder=out/key;folder.mkdir(exist_ok=True)
            try:
                if '.pdf' in url.lower():
                    resp=c.request.get(url,timeout=PAGE_LOAD_TIMEOUT_MS)
                    if not resp.ok:raise ValueError('HTTP '+str(resp.status))
                    content=resp.body();(folder/'source.pdf').write_bytes(content);doc=pymupdf.open(stream=content,filetype='pdf')
                    r=dict(bank=bank,url=url,text='\n'.join(pg.get_text() for pg in doc),kind='pdf',pages=len(doc))
                else:
                    p=c.new_page();p.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS);p.wait_for_timeout(PAGE_SETTLE_MS)
                    r=dict(bank=bank,url=p.url,text=p.locator('body').inner_text(),kind='html',tables=[dict(index=i,rows=t.evaluate(PHYSICAL),visible=t.is_visible()) for i,t in enumerate(p.locator('table').all())],links=p.locator('a[href]').evaluate_all('xs=>xs.map(x=>({text:x.innerText.trim(),url:x.href}))'))
                    (folder/'source.html').write_text(p.content(),encoding='utf8');p.screenshot(path=str(folder/'page.png'),full_page=True);p.close()
                save(folder/'source.json',r);(folder/'source.txt').write_text(r['text'],encoding='utf8');print(key,r['kind'],len(r['text']),flush=True)
            except Exception as e:save(folder/'error.json',dict(url=url,error=str(e)));print(key,'FAILED',str(e)[:100],flush=True)
        b.close()

if __name__=='__main__':main()

"""Local browser capture of selected HLB/SBI board tables and eligibility."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
from datetime import datetime,timezone,timedelta
from pathlib import Path
import argparse,hashlib
from playwright.sync_api import sync_playwright
from market_rates.common import save,digest
from market_rates.link_registry import entries
from market_rates.pipeline import evidence_index

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out)
    if out.exists():raise ValueError('Use a new capture directory')
    evidence=out/'evidence';evidence.mkdir(parents=True);sources=entries('../利率链接.xlsx')
    def source(bank,hint):
        found=[r for r in sources if r['bank']==bank and r['currency_hint']==hint and r['rate_type']=='board' and r['url']]
        if len(found)!=1:raise ValueError('Missing or ambiguous registry source: '+bank+'/'+hint)
        return found[0]
    pages=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},locale='en-SG')
        def open_page(url,bank,label):
            from urllib.parse import urlsplit
            page=context.new_page();domain=urlsplit(url).hostname
            def guard(route):
                if route.request.is_navigation_request() and urlsplit(route.request.url).hostname!=domain:route.abort()
                else:route.continue_()
            page.route('**/*',guard)
            response=page.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS);page.wait_for_timeout(PAGE_SETTLE_MS)
            if not response or response.status>=400:raise ValueError('Official page unavailable: '+url)
            text=page.locator('body').inner_text()
            if any(s in text.lower() for s in ['access denied','verify you are human','captcha']):raise ValueError('Blocked official page')
            (evidence/(label+'.html')).write_text(page.content(),encoding='utf8')
            (evidence/(label+'.full.txt')).write_text(text,encoding='utf8')
            return page
        def record(page,bank,currency,label,regions,table):
            images=[];texts=[]
            for i,region in enumerate(regions):
                if region.count()!=1 or not region.is_visible():raise ValueError('Evidence region not uniquely visible: '+label)
                name=f'{label}-{i+1}.png';region.screenshot(path=str(evidence/name),animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS);images.append(name);texts.append(region.inner_text())
            grid=table.evaluate('(t)=>[...t.rows].map(r=>[...r.cells].map(c=>c.innerText.trim()))')
            text='\n\n'.join(texts);(evidence/(label+'.txt')).write_text(text,encoding='utf8')
            pages.append(dict(id=label,bank=bank,currency=currency,rate_type='board',url=page.url,
                text=text,images=images,grid=grid,ok=True,complete=True,capture_scope='configured_units',
                product_ids=[bank.lower()+'-'+currency.lower()+'-board'],captured_at=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(text.encode()).hexdigest(),image_hashes={name:hashlib.sha256((evidence/name).read_bytes()).hexdigest() for name in images}))
        try:
            rates=open_page(source('HLB','SGD')['url'],'HLB','hlb-rates')
            links=rates.locator('a[href]').evaluate_all('els=>els.map(e=>({text:e.innerText,url:e.href}))')
            product_urls=list(dict.fromkeys(x['url'] for x in links if x['text'].strip()=='Fixed Deposit Account'))
            if len(product_urls)!=1:raise ValueError('HLB SGD linked product page ambiguous')
            for currency in ['SGD','USD']:
                rates.locator('.fd-dropdown select').select_option(currency);rates.wait_for_timeout(PAGE_SETTLE_MS)
                table=rates.locator(f'table[data-for-currency="{currency}"]')
                record(rates,'HLB',currency,'hlb-'+currency.lower()+'-rates',[rates.locator('.rate-tables').locator('..')],table)
                product=open_page(product_urls[0] if currency=='SGD' else source('HLB','others')['url'],'HLB','hlb-'+currency.lower()+'-product')
                eligibility=product.get_by_text('Eligibility',exact=True).locator('..')
                regions=[eligibility]
                if currency=='USD':regions.append(product.locator('table').filter(has_text='Minimum placement amount'))
                record(product,'HLB',currency,'hlb-'+currency.lower()+'-terms',regions,product.locator('table').filter(has_text='Minimum placement amount') if currency=='USD' else table)
                # SGD product has no amount table; do not associate the rates grid with eligibility.
                if currency=='SGD':pages[-1]['grid']=[]
                product.close()
            rates.close()
            sbi=open_page(source('SBI','SGD')['url'],'SBI','sbi-rates')
            table=sbi.locator('table').filter(has_text='SGD Term Deposit with effect')
            record(sbi,'SBI','SGD','sbi-sgd-rates',[table],table)
            sbi.locator('a[href="#uk-trade-tab2"]').first.click(timeout=CONTENT_TIMEOUT_MS);sbi.wait_for_timeout(PAGE_SETTLE_MS)
            table=sbi.locator('table').filter(has_text='USD deposit rates with effect')
            record(sbi,'SBI','USD','sbi-usd-rates',[table],table)
            (evidence/'sbi-fx-visible.txt').write_text(sbi.locator('#uk-trade-tab2').inner_text(),encoding='utf8')
            sbi.close()
        finally:browser.close()
    now=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    run=dict(id=out.name,as_of=now,demo=False,pages=pages,errors=[],metadata=[],bank_dates={'HLB':now,'SBI':now},
        evidence_hash=digest(pages),pilot=dict(no_publication=True,scope='HLB/SBI SGD/USD board pilot'),
        rate_scopes=[dict(currency=c,rate_type='board') for c in ['SGD','USD']])
    save(out/'run.json',run);save(out/'link-snapshot.json',sources);evidence_index(pages,evidence)
    print({'pages':len(pages),'images':sum(len(p['images']) for p in pages),'out':str(out)},flush=True)

if __name__=='__main__':main()

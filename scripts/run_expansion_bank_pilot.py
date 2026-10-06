"""UOB / ICBC / BOC: discover current public promotion pages from the link book."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
from datetime import datetime,timezone,timedelta
from pathlib import Path
import re
from urllib.parse import urlsplit
from market_rates.common import load,save
from market_rates.capture import allowed
from market_rates.xlsx_read import read_xlsx
from market_rates.boc_discovery import latest_promotion_url

BANKS={'UOB':('A75','D77','uob-sgd-promo','UOB SGD Fixed Deposit Promotion'),
       'ICBC':('A40','D42','icbc-sgd-promo','ICBC SGD Fixed Deposit Promotion'),
       'BOC':('A7','D9','boc-sgd-mobile','BOC SGD Mobile Fixed Deposit')}

def configuration(links,out):
    from playwright.sync_api import sync_playwright
    cells=next(iter(read_xlsx(links,merge_anchors_only=True).values()))
    cfg=load('config/project.local.json');cfg['models'].update(num_ctx=32768,num_predict=8192)
    cfg.update(extraction_profile='multi-bank-literal-v1',transcribe_rate_units=True,expected_banks=list(BANKS),products=[],sources=[],
       tenor_map={'UOB/uob-sgd-promo/10M':'9M','BOC/boc-sgd-welcome/4M':'3M','BOC/boc-sgd-welcome/8M':'9M'},
       pilot=dict(no_publication=True,scope='UOB, ICBC, BOC SGD flat-rate promotions; board and step-up excluded'))
    out=Path(out);out.mkdir(parents=True)
    today=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            for bank,(anchor,cell,pid,name) in BANKS.items():
                if cells.get(anchor)!=bank:raise ValueError('Bank-link mapping changed: '+anchor)
                url=cells[cell];domain=urlsplit(url).hostname
                domains=[domain]+(['v.icbc.com.cn'] if bank=='ICBC' else [])
                cfg['products'].append(dict(id=pid,bank=bank,name=name,personal_status='unknown',expected=True))
                page=browser.new_page(viewport={'width':1440,'height':1100},locale='en-SG')
                try:
                    def guard(route):
                        if route.request.is_navigation_request() and not allowed(route.request.url,domains):route.abort()
                        else:route.continue_()
                    page.route('**/*',guard)
                    response=page.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                    page.wait_for_timeout(PAGE_SETTLE_MS)
                    if not response or response.status>=400:raise ValueError('Official page unavailable: '+url)
                    refs=page.locator('a[href]').evaluate_all('els=>els.map(e=>({text:e.innerText,url:e.href}))')
                    save(out/(bank+'.json'),dict(url=url,links=refs,captured_at=datetime.now(timezone.utc).isoformat()))
                    if bank=='BOC':
                        url=latest_promotion_url(refs,today)
                finally:page.close()
                def source(key,u,**extra):
                    if not allowed(u,domains):raise ValueError('Unregistered official campaign domain: '+u)
                    return dict(id=key,bank=bank,enabled=True,urls=[u],domains=domains,max_depth=0,max_pages=1,product_ids=[pid],**extra)
                def unit(selector,product=pid,kind='rates'):return dict(selector=selector,product_ids=[product],kind=kind)
                if bank=='UOB':
                    cfg['sources'].append(source('UOB-rates',url,capture_units=[unit('#rates.uob-adaptive-table .desktop-table-container')],settle_ms=1500,dismiss_selectors=['.dy-custom-close-btn:visible']))
                    for tenor in [6,10,12]:
                        urls=list(dict.fromkeys(v['url'] for v in refs if v['text'].strip()==f'{tenor}-month Promotional Interest Rate'))
                        if len(urls)!=1:raise ValueError('Missing/ambiguous UOB terms')
                        s=source(f'UOB-terms-{tenor}',urls[0]);s['tenor_scope']=tenor;cfg['sources'].append(s)
                elif bank=='ICBC':
                    cfg['sources'].append(source('ICBC-rates',url,capture_units=[
                        unit('#AD5con1 table:not(:has(table)):has-text("Counter Promotion")'),
                        unit('#AD5con1 table:not(:has(table)):has-text("E-Banking")')]))
                    urls=list(dict.fromkeys(v['url'] for v in refs if urlsplit(v['url']).path.endswith('/1fixeddepositpromotion.pdf')))
                    if len(urls)!=1:raise ValueError('Missing ICBC fixed deposit terms')
                    cfg['sources'].append(source('ICBC-terms',urls[0]))
                else:
                    welcome='boc-sgd-welcome';cfg['products'].append(dict(id=welcome,bank=bank,name='BOC New Customer SGD Fixed Deposit',personal_status='unknown',expected=True))
                    cfg['sources'].append(source('BOC-rates',url,device_scale_factor=3,capture_units=[
                        unit('.trs_editor_view > table:nth-of-type(1)',welcome),
                        dict(**unit('.trs_editor_view > table:nth-of-type(2)'),end_before='tr:has(td:text-is("美元"))',end_before_text='美元'),
                        unit('.trs_editor_view > ul',pid,'terms'),unit('.trs_editor_view > ul',welcome,'terms')]))
        finally:browser.close()
    return cfg

if __name__=='__main__':
    # Reuse the checked extraction/resume/evidence orchestration, not its bank config.
    import scripts.run_next_bank_pilot as runner
    runner.BANKS=BANKS;runner.configuration=configuration;runner.main()

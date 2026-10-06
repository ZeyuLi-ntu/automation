"""OCBC / HL Bank / SBI: discover official linked terms on every fresh run."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse
from datetime import datetime,timezone,timedelta
from pathlib import Path
import re
from urllib.parse import urlsplit
from market_rates.common import load,save,digest
from market_rates.capture import capture_sources,allowed
from market_rates.xlsx_read import read_xlsx
from market_rates.model_adapter import preflight,extract
from market_rates.pipeline import check_evidence,evidence_index,evaluate
from market_rates.store import Store

BANKS={'OCBC':('A50','D52','ocbc-sgd-promo','SGD Time Deposit Promotion','#section-rates'),
       'HLB':('A25','D27','hlb-sgd-promo','HL Bank SGD Fixed Deposit Promotion','table:has-text("Minimum Placement Amount")'),
       'SBI':('A70','D72','sbi-sgd-promo','SBIS SGD Term Deposit Promotion','#column-2:has(.inner-page-content table)')}

def configuration(links,out):
    from playwright.sync_api import sync_playwright
    cells=next(iter(read_xlsx(links,merge_anchors_only=True).values()))
    cfg=load('config/project.local.json');cfg['models'].update(num_ctx=32768,num_predict=8192)
    cfg.update(extraction_profile='multi-bank-literal-v1',transcribe_rate_units=True,expected_banks=list(BANKS),products=[],sources=[],pdf_rate_products=['hlb-sgd-promo'],pdf_rate_pages={'hlb-sgd-promo':[1]},pilot=dict(no_publication=True,scope='OCBC, HLB, SBI SGD promotions and linked campaign terms'))
    out=Path(out);out.mkdir(parents=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            for bank,(anchor,cell,pid,name,selector) in BANKS.items():
                if cells.get(anchor)!=bank:raise ValueError('Bank-link mapping changed: '+anchor)
                url=cells[cell];domain=urlsplit(url).hostname
                cfg['products'].append(dict(id=pid,bank=bank,name=name,personal_status='unknown',expected=True))
                page=browser.new_page(viewport={'width':1440,'height':1100},locale='en-SG')
                try:
                    def guard(route):
                        if route.request.is_navigation_request() and not allowed(route.request.url,[domain]):route.abort()
                        else:route.continue_()
                    page.route('**/*',guard)
                    response=page.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                    page.wait_for_timeout(PAGE_SETTLE_MS)
                    if not response or response.status>=400:raise ValueError('Official page unavailable: '+url)
                    refs=page.locator('a[href]').evaluate_all('els=>els.map(e=>({text:e.innerText,url:e.href}))')
                    save(out/(bank+'.json'),dict(url=url,links=refs,captured_at=datetime.now(timezone.utc).isoformat()))
                finally:page.close()
                def source(key,u,**extra):
                    if not allowed(u,[domain]):raise ValueError('Unregistered campaign domain')
                    return dict(id=key,bank=bank,enabled=True,urls=[u],domains=[domain],max_depth=0,max_pages=1,product_ids=[pid],**extra)
                units=[dict(selector=selector,product_ids=[pid],kind='terms' if bank=='HLB' else 'rates')]
                if bank=='HLB':units.append(dict(selector='.promotioncategoryanddate',product_ids=[pid],kind='terms'))
                cfg['sources'].append(source(bank+'-rates',url,capture_units=units,settle_ms=1500))
                patterns={'OCBC':[(r'^Terms and conditions governing OCBC SGD Time Deposit Promotional\s+Rates$','primary')],
                          'HLB':[(r'^Online FD Terms & Conditions$','primary'),(r'^Branch FD Terms & Conditions$','primary'),(r'^SA FD HK Terms & Conditions$','bonus')],
                          'SBI':[]}[bank]
                for n,(pattern,role) in enumerate(patterns):
                    urls=list(dict.fromkeys(x['url'] for x in refs if re.search(pattern,x['text'].strip(),re.I)))
                    if len(urls)!=1:raise ValueError('Campaign link missing or ambiguous: '+pattern)
                    cfg['sources'].append(source(bank+'-terms-'+str(n),urls[0],terms_role=role))
        finally:browser.close()
    return cfg

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--links',default='../利率链接.xlsx');p.add_argument('--resume',action='store_true');p.add_argument('--capture-only',action='store_true');p.add_argument('--reprocess',action='store_true');p.add_argument('--bank',choices=list(BANKS));a=p.parse_args()
    root=Path(a.out)
    if not a.resume:
        if root.exists():raise ValueError('Use a new run folder')
        status=preflight(load('config/project.local.json'));root.mkdir(parents=True)
        cfg=configuration(a.links,root/'discovery');save(root/'config.snapshot.json',cfg)
        pages,errors=capture_sources(cfg,root/'evidence')
        run=dict(id=root.name,as_of=datetime.now(timezone(timedelta(hours=8))).date().isoformat(),demo=False,pages=pages,errors=errors,metadata=[],model_status=status,evidence_hash=digest(pages),pilot=cfg['pilot'])
        save(root/'run.json',run);evidence_index(pages,root/'evidence');print({'pages':len(pages),'errors':errors},flush=True)
        if errors:raise ValueError('Capture errors must be resolved before extraction')
    else:
        run=load(root/'run.json');cfg=load(root/'config.snapshot.json');check_evidence(run,root/'evidence')
        if any(not e.startswith('TERMS_REVIEW:') for e in run['errors']):raise ValueError('Capture errors must be resolved before extraction')
    if a.capture_only:return
    for bank in ([a.bank] if a.bank else cfg['expected_banks']):
        for lane in ['llm','vlm']:
            path=root/f'model-{bank}-{lane}.json'
            if path.exists():
                if not a.reprocess:continue
                path.rename(path.with_name(path.stem+'-previous-'+datetime.now().strftime('%H%M%S%f')+'.json'))
            print('Extracting',bank,lane,flush=True)
            result,meta=extract(lane,[x for x in run['pages'] if x['bank']==bank],root/'evidence',cfg,run['as_of'])
            save(path,dict(result=result,metadata=dict(meta,bank=bank)));print({'bank':bank,'lane':lane,'offers':len(result['offers']),'unreadable':result['unreadable']},flush=True)
    run['metadata']=[]
    for lane in ['llm','vlm']:
        run[lane]=dict(offers=[],inventory=[],coverage_complete=True,unreadable=[])
        for bank in cfg['expected_banks']:
            path=root/f'model-{bank}-{lane}.json'
            if not path.exists():run[lane]['coverage_complete']=False;run[lane]['unreadable'].append(bank+' missing route');continue
            value=load(path);run['metadata'].append(value['metadata'])
            for field in ['offers','inventory','unreadable']:run[lane][field]+=value['result'][field]
            run[lane]['coverage_complete'] &= value['result']['coverage_complete']
    run['errors']=[e for e in run['errors'] if not e.startswith('TERMS_REVIEW:')]+['TERMS_REVIEW: '+b+' Full campaign terms pending review' for b in cfg['expected_banks']]
    save(root/'run.json',run)
    store=Store(root/'pilot.sqlite3')
    try:result=evaluate(root,store);print({'pending':result['pending']},flush=True)
    finally:store.close()

if __name__=='__main__':main()

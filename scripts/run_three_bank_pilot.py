"""Three additional banks: frozen official evidence and independent local lanes."""
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from market_rates.common import load, save, digest
from market_rates.xlsx_read import read_xlsx
from market_rates.capture import capture_sources
from market_rates.pipeline import check_evidence, evidence_index, evaluate
from market_rates.model_adapter import preflight, extract
from market_rates.store import Store

PRODUCTS = [
 ('rhb-sgd-promo','RHB','SGD Fixed Deposit Campaign','present'),
 ('cimb-sgd-online','CIMB','SGD Online Fixed Deposit','present'),
 ('cimb-wwfd-online','CIMB','Why Wait Fixed Deposit-i Online','present'),
 ('cimb-preferred-welcome','CIMB','New-to-Preferred Welcome FD / WWFD-i','absent'),
 ('hlf-branch-promo','HLF','Fixed Deposit Promotion','present'),
 ('hlf-digital-promo','HLF','Online Fixed Deposit Special','present')]

def config_for(links,discovery_dir='runs/three-bank-discovery'):
    from market_rates.table_validation import sha
    c = load('config/project.local.json')
    c['models'].update(num_ctx=32768, num_predict=8192, max_text_chars=20000, max_images=1)
    c['extraction_profile'] = 'multi-bank-literal-v1'
    c['expected_banks'] = ['RHB','CIMB','HLF']
    c['products'] = [dict(id=i,bank=b,name=n,personal_status=s,expected=True) for i,b,n,s in PRODUCTS]
    name, cells = next(iter(read_xlsx(links).items()))
    for anchor,bank in [('A55','RHB'),('A12','CIMB'),('A30','HLF')]:
        if cells.get(anchor)!=bank:raise ValueError('Link-workbook bank mapping changed: '+anchor)
    def url(cell):
        u = urlsplit(cells[cell]); return urlunsplit((u.scheme,u.netloc,u.path,'',''))
    def source(bank, key, u, units=None, products=None):
        official={'RHB':{'rhbgroup.com.sg','www.rhbgroup.com.sg'},'CIMB':{'www.cimb.com.sg','www.cimbpreferred.com.sg'},'HLF':{'www.hlf.com.sg'}}
        if urlsplit(u).scheme!='https' or urlsplit(u).hostname not in official[bank]:raise ValueError('Unregistered bank domain: '+u)
        return dict(id=key, bank=bank,enabled=True,domains=[urlsplit(u).hostname],urls=[u],max_pages=1,max_depth=0,
                    capture_units=units or [],product_ids=products or [],settle_ms=3000 if bank=='HLF' else 0)
    def unit(selector, product, kind='rates'):
        return dict(selector=selector,product_ids=[product],kind=kind)
    c['sources'] = [
        source('RHB','rhb-d57',url('D57'),[unit('#PromotionalRates-FDC','rhb-sgd-promo')]),
        source('CIMB','cimb-d14',url('D14'),[
            unit('.cmp-table:has-text("PERSONAL BANKING"):has-text("ONLINE PROMO")','cimb-sgd-online'),
            unit('.cmp-table:has-text("WWFD-i Online Promo")','cimb-wwfd-online')]),
        source('HLF','hlf-d32',url('D32'),[unit('#promo1','hlf-branch-promo'),unit('#promo2','hlf-digital-promo')])]
    c['sources'][1]['expand_selectors']=['text=Accept and Close']
    # Discovered links are read from archived official pages, not generated from dates.
    def discovered(directory, pattern):
        found = list(dict.fromkeys(l['url'] for l in load(Path(discovery_dir)/directory/'inspection.json')['links'] if pattern in l['url']))
        if not found: raise ValueError('Missing official discovered link: '+pattern)
        if len(found)>1:raise ValueError('Ambiguous campaign links require review: '+pattern)
        return found[0]
    # The main promotional anchor includes a broken /rhb/dam alias. The separate
    # Terms & Conditions section links the actual /dam resource; preserve both in discovery.
    rhb_links=list(dict.fromkeys(l['url'] for l in load(Path(discovery_dir)/'RHB/inspection.json')['links'] if '/dam/jcr:' in l['url'] and '/rhb/dam' not in l['url'] and 'Fixed%20Deposit' in l['url']))
    if len(rhb_links)!=1:raise ValueError('RHB campaign PDF link changed or is ambiguous')
    rhb=rhb_links[0]
    c['sources'].append(source('RHB','rhb-promo-terms',rhb,products=['rhb-sgd-promo']))
    for directory,pattern,ids in [
        ('CIMB-product','tnc-sgfd-2026.pdf',['cimb-sgd-online']),
        ('CIMB-wwfd','tnc-wwfd-2026.pdf',['cimb-wwfd-online']),
        ('CIMB-wwfd','wwfd-i-promo.pdf',['cimb-wwfd-online']),
        ('CIMB-preferred','ntp-fd.pdf',['cimb-preferred-welcome'])]:
        s=source('CIMB',pattern,discovered(directory,pattern),products=ids)
        if pattern=='wwfd-i-promo.pdf':s['terms_role']='bonus'
        if pattern=='ntp-fd.pdf': s['pdf_rates']=True
        c['sources'].append(s)
    c['pdf_rate_products'] = ['cimb-preferred-welcome']
    c['pdf_rate_pages'] = {'cimb-preferred-welcome':[1]}
    c['pilot'] = dict(no_publication=True,scope='RHB campaign; CIMB online FD, WWFD-i and welcome campaign; HLF two promotions',
        input_workbook=str(Path(links).resolve()),workbook_sha256=sha(links),sheet=name,cells=['D57','D14','D32'],
        limitations=['General banking agreements and unlinked/private/offline offers are outside this pilot. Cash gifts remain conditions, not annualised interest.'])
    return c

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--links',default='../利率链接.xlsx')
    p.add_argument('--capture-only',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--bank',choices=['RHB','CIMB','HLF']);p.add_argument('--lane',choices=['llm','vlm'])
    p.add_argument('--reprocess',action='store_true',help='Preserve earlier result files, rebind cached matching raw requests')
    a=p.parse_args(); folder=Path(a.out)
    if not a.resume:
        if folder.exists(): raise ValueError('Use a new run folder to preserve audit history')
        status=preflight(load('config/project.local.json'));folder.mkdir(parents=True)
        from market_rates.three_bank_discovery import discover
        directory=discover(a.links,folder/'discovery')
        cfg=config_for(a.links,directory)
        save(folder/'config.snapshot.json',cfg)
        pages,errors=capture_sources(cfg,folder/'evidence')
        run=dict(id='three-bank-'+datetime.now().strftime('%Y%m%d-%H%M%S'),as_of=datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
                 demo=False,pages=pages,errors=errors,metadata=[],model_status=status,created_at=datetime.now(timezone.utc).isoformat(),
                 evidence_hash=digest(pages),pilot=cfg['pilot'])
        save(folder/'run.json',run);evidence_index(pages,folder/'evidence')
        print({'pages':len(pages),'images':sum(len(p['images']) for p in pages),'errors':errors},flush=True)
    else:
        run=load(folder/'run.json');cfg=load(folder/'config.snapshot.json');check_evidence(run,folder/'evidence')
    if a.capture_only:return
    for bank in ([a.bank] if a.bank else cfg['expected_banks']):
        pages=[p for p in run['pages'] if p['bank']==bank]
        for lane in ([a.lane] if a.lane else ['llm','vlm']):
            path=folder/f'model-{bank}-{lane}.json'
            if path.exists():
                if not a.reprocess:continue
                path.rename(path.with_name(path.stem+'-previous-'+datetime.now().strftime('%H%M%S')+'.json'))
            print('Extracting',bank,lane,flush=True)
            try:
                result,meta=extract(lane,pages,folder/'evidence',cfg,run['as_of'])
                meta['bank']=bank;save(path,dict(result=result,metadata=meta))
                print({'bank':bank,'lane':lane,'offers':len(result['offers']),'unreadable':result['unreadable']},flush=True)
            except Exception as exc:
                save(folder/f'failure-{bank}-{lane}-{datetime.now().strftime("%H%M%S")}.json',dict(error=str(exc)))
                print(bank,lane,type(exc).__name__,str(exc),flush=True)
    run=load(folder/'run.json')
    run['metadata']=[]
    for lane in ['llm','vlm']:
        run[lane]=dict(offers=[],inventory=[],coverage_complete=True,unreadable=[])
        for bank in cfg['expected_banks']:
            path=folder/f'model-{bank}-{lane}.json'
            if not path.exists():
                run[lane]['coverage_complete']=False;run[lane]['unreadable'].append(bank+' missing route');continue
            x=load(path);run['metadata'].append(x['metadata'])
            for field in ['offers','inventory','unreadable']:run[lane][field].extend(x['result'][field])
            run[lane]['coverage_complete'] &= x['result']['coverage_complete']
    run['errors']=[e for e in run['errors'] if not e.startswith('TERMS_REVIEW:')]
    for meta in run['metadata']:
        for msg in meta.get('review_required',[]):
            message='TERMS_REVIEW: '+meta['bank']+' '+msg
            if message not in run['errors']:run['errors'].append(message)
    save(folder/'run.json',run)
    store=Store(folder/'pilot.sqlite3')
    try:
        result=evaluate(folder,store);print({'pending':result['pending'],'approved_groups':len(result['groups'])},flush=True)
    finally:store.close()

if __name__=='__main__':main()

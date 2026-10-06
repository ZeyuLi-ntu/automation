"""ICBC tab-specific board tables and HLF's Board/Special Rates table."""
import argparse,re
from playwright.sync_api import sync_playwright
from market_rates.board_capture import BoardCapture
from market_rates.browser_wait import CONTENT_TIMEOUT_MS, PAGE_SETTLE_MS
from market_rates.link_registry import entries

def capture(out,banks=None):
    batch=BoardCapture(out);registry=entries('../利率链接.xlsx');banks=banks or ['ICBC','HLF']
    def url(bank):
        values={x['url'] for x in registry if x['bank']==bank and x['rate_type']=='board' and x['url']}
        if len(values)!=1:raise ValueError('Expected one registered board URL for '+bank)
        return values.pop()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--disable-http2'])
        ctx=browser.new_context(viewport={'width':1600,'height':1600},device_scale_factor=2,locale='en-SG')
        try:
            if 'ICBC' in banks:
                for cur,label in [('SGD','SGD Fixed Deposit'),('CNY','RMB Fixed Deposit'),('USD','USD Fixed Deposit')]:
                    p,page=batch.open(ctx,'ICBC','icbc-'+cur,url('ICBC'))
                    p.get_by_text(label,exact=True).filter(visible=True).first.click(timeout=CONTENT_TIMEOUT_MS);p.wait_for_timeout(PAGE_SETTLE_MS)
                    heading=p.get_by_text(re.compile(r'(?:SGD|RMB|USD)\s+Fixed Deposit interest board rate',re.I)).filter(visible=True).last
                    title_id,title=batch.text(p,page,'icbc-'+cur+'-title',heading)
                    table=heading.locator('xpath=following::table[1]');rows,ids=batch.table(p,page,'icbc-'+cur+'-table',table)
                    if ('RMB' if cur=='CNY' else cur) not in rows[0][0] or not rows[0][0].startswith('Amount'):raise ValueError('Wrong ICBC board table')
                    extra=[title];ids.append(title_id)
                    if cur=='CNY':
                        pattern=r'^The minimum deposit amount over counter is RMB'
                        tid,ev=batch.text(p,page,'icbc-'+cur+'-minimum',p.get_by_text(re.compile(pattern)).filter(visible=True).last)
                        if ('RMB500' if cur=='CNY' else 'USD500') not in ev['quote'].replace(' ',''):raise ValueError('ICBC page minimum changed')
                        ids.append(tid);extra.append(ev)
                    batch.sections.append(dict(id=batch.prefix+'icbc-'+cur,bank='ICBC',currency=cur,product_id='icbc-board-90' if cur=='SGD' else 'icbc-'+cur.lower()+'-board',layout='icbc-board',rows=rows,task_ids=ids,page_id=page['id'],extra_evidence=extra,minimum='500' if cur=='CNY' else None))
                    batch.finish(p,page);p.close();print('ICBC',cur,'board captured',flush=True)
            if 'HLF' in banks:
                p,page=batch.open(ctx,'HLF','hlf-sgd',url('HLF'))
                tables=p.locator('table').filter(has_text='Board Rates').filter(has_text='Special Rates').filter(visible=True)
                if tables.count()!=1:raise ValueError('HLF Board/Special table missing or ambiguous')
                rows,ids=batch.table(p,page,'hlf-sgd-table',tables.first);extra=[]
                for name,txt in [('minimum','Minimum placement sum for 1 or 2 months deposit is S$10,000, and for the longer terms is S$500.'),('ceiling','For sums of S$1 million and higher, please enquire at our branches for rates.')]:
                    tid,ev=batch.text(p,page,'hlf-'+name,p.get_by_text(txt,exact=True));ids.append(tid);extra.append(ev)
                batch.sections.append(dict(id=batch.prefix+'hlf-sgd',bank='HLF',currency='SGD',product_id='hlf-sgd-board',table=0,rows=rows,task_ids=ids,page_id=page['id'],extra_evidence=extra))
                batch.finish(p,page);p.close();print('HLF Board/Special captured',flush=True)
        finally:browser.close()
    return batch.save()

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);a.add_argument('--banks');x=a.parse_args();capture(x.out,x.banks.split(',') if x.banks else None)

"""OCBC live board tables, linked terms and placement minima; original pixels."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse, hashlib, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright
from market_rates.common import save, digest
from market_rates.link_registry import entries
from market_rates.pipeline import evidence_index
from scripts.capture_board_wave import PHYSICAL, shot

REQUIRED = {'SGD', 'USD', 'AUD', 'NZD', 'CAD', 'HKD', 'EUR', 'GBP'}
PRODUCT = 'https://www.ocbc.com/personal-banking/deposits/fixed-deposit-account'
TERMS = 'https://www.ocbc.com/personal-banking/terms-and-conditions/terms-and-conditions-governing-deposit-accounts'


def capture(out, links):
    out = Path(out); ev = out/'evidence'; ev.mkdir(parents=True, exist_ok=False)
    stamp = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    prefix = out.name+'-'; pages = []; tasks = []; sections = []; coverage = []
    registered = [e for e in entries(links) if e['bank']=='OCBC' and e['rate_type']=='board' and e['url']]
    if len(registered)!=2: raise ValueError('Expected OCBC SGD and FX links in the link workbook')
    sgd = next(e for e in registered if 'fixed-deposit-sgd' in e['url'])
    fx = next(e for e in registered if e is not sgd)

    def add_task(page, name, expected, images, kind='grid'):
        t = dict(id=prefix+name, bank='OCBC', kind=kind, expected=expected,
                 images=images, page_id=page['id'], image_hashes={n:hashlib.sha256((ev/n).read_bytes()).hexdigest() for n in images})
        tasks.append(t); page['images'] += images; page['image_hashes'].update(t['image_hashes'])
        return t['id']

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--disable-http2'])
        ctx = browser.new_context(viewport={'width':1800, 'height':1600}, device_scale_factor=2, locale='en-SG')
        def open_page(name, url):
            p = ctx.new_page(); response = p.goto(url, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT_MS)
            if not response or response.status!=200: raise ValueError('OCBC source unavailable: '+url)
            p.wait_for_timeout(PAGE_SETTLE_MS)
            record = dict(id=prefix+name, bank='OCBC', currency='multi', rate_type='board', url=p.url,
                          captured_at=stamp, ok=True, complete=True, images=[], image_hashes={})
            return p, record
        def finish(p, record):
            record['text']=p.locator('body').inner_text(); record['sha256']=hashlib.sha256(record['text'].encode()).hexdigest()
            (ev/(record['id']+'.html')).write_text(p.content(),encoding='utf8')
            (ev/(record['id']+'.txt')).write_text(record['text'],encoding='utf8')
            pages.append(record); p.close()
        def metadata(p, record, name, locator):
            locator = locator.filter(visible=True).first
            text = locator.inner_text().strip(); fn=prefix+name+'.png'; shot(p,locator,ev/fn)
            return add_task(record,name,text,[fn],'text'), dict(page_id=record['id'],quote=text,locator=name)
        def table_tasks(p, record, name, table):
            rows=table.evaluate(PHYSICAL); ids=[]
            table.evaluate("e=>{window.__ocbcFloat=[...document.querySelectorAll('*')].filter(x=>x!==e&&!x.contains(e)&&!e.contains(x)&&['fixed','sticky'].includes(getComputedStyle(x).position)).map(x=>[x,x.style.visibility]);window.__ocbcFloat.forEach(([x])=>x.style.visibility='hidden')}")
            trs=[tr for tr in table.locator('tr').all() if tr.evaluate('r=>[...r.cells].some(c=>c.innerText.trim())')]
            if len(trs)!=len(rows): raise ValueError('Unexpected physical table structure')
            # Two rows per original screenshot keep all decimals readable locally.
            groups=([(0,1),(1,1)]+[(i,2) for i in range(2,len(trs),2)]) if name=='sgd-table' else [(i,2) for i in range(0,len(trs),2)]
            for i,count in groups:
                group=trs[i:i+count]; group[0].scroll_into_view_if_needed()
                p.evaluate('(dy)=>window.scrollBy(0,dy)',group[0].bounding_box()['y']-200)
                pieces=[(group,rows[i:i+count])]
                if name=='sgd-table' and i==0:
                    cells=trs[0].locator(':scope > th, :scope > td').all()
                    pieces=[(cells[j:j+4],[rows[0][j:j+4]]) for j in range(0,len(cells),4)]
                for part,(elements,expected) in enumerate(pieces):
                    boxes=[tr.bounding_box() for tr in elements]
                    x=min(b['x'] for b in boxes); y=min(b['y'] for b in boxes)
                    right=max(b['x']+b['width'] for b in boxes); bottom=max(b['y']+b['height'] for b in boxes)
                    if y<0 or bottom>p.viewport_size['height']:raise ValueError('Evidence rows extend beyond viewport')
                    label=name+'-'+str(i)+('-part'+str(part) if len(pieces)>1 else '')
                    fn=prefix+label+'.png'
                    p.screenshot(path=str(ev/fn),clip=dict(x=x,y=y,width=right-x,height=bottom-y),animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS)
                    ids.append(add_task(record,label,expected,[fn]))
            p.evaluate('()=>window.__ocbcFloat.forEach(([x,v])=>x.style.visibility=v)')
            return rows, ids
        try:
            p, product = open_page('product',PRODUCT)
            p.locator('a[href="#document-apply-online"]').click(timeout=CONTENT_TIMEOUT_MS)
            minimum_loc=p.locator('#document-apply-online .item-list').filter(has=p.get_by_text('Minimum placement:',exact=True))
            minimum_task, minimum_evidence=metadata(p,product,'minimum',minimum_loc)
            if '$50,000 in HKD currency' not in minimum_evidence['quote']:raise ValueError('OCBC placement minima changed')
            finish(p,product)

            p, terms = open_page('terms',TERMS)
            p.locator('#interest .accordion__item__title').click(timeout=CONTENT_TIMEOUT_MS)
            basis_task, basis_evidence=metadata(p,terms,'annual-day-count',p.locator('p').filter(has_text=re.compile(r'^5\.1 Where applicable')))
            if '365-day or a 360-day basis' not in basis_evidence['quote']:raise ValueError('OCBC governing interest basis changed')
            finish(p,terms)

            p, record=open_page('sgd',sgd['url']); p.locator('table').first.wait_for(state='visible',timeout=CONTENT_TIMEOUT_MS)
            p.wait_for_function("()=>[...document.querySelectorAll('table')].some(t=>t.innerText.includes('S$5,000')&&t.innerText.includes('0.'))",timeout=CONTENT_TIMEOUT_MS)
            table=p.locator('table').first; rows, ids=table_tasks(p,record,'sgd-table',table)
            foot_task, foot_evidence=metadata(p,record,'sgd-renewal',p.locator('p').filter(has_text=re.compile(r'^\*Please note that new placements')))
            sections.append(dict(id=prefix+'sgd',bank='OCBC',currency='SGD',product_id='ocbc-sgd-board',layout='ocbc-sgd',rows=rows,
                task_ids=ids+[basis_task,foot_task],page_id=record['id'],rate_basis='annual_nominal',basis_evidence=[basis_evidence,foot_evidence]))
            finish(p,record); print('OCBC SGD captured',flush=True)

            p, record=open_page('fx',fx['url'])
            p.wait_for_function("()=>document.querySelectorAll('.foreign-currency table').length>=8 && [...document.querySelectorAll('.foreign-currency table')].every(t=>t.rows.length>=6)",timeout=CONTENT_TIMEOUT_MS)
            date_task,date_evidence=metadata(p,record,'fx-as-of',p.get_by_text(re.compile(r'^Daily prices as at')).filter(visible=True))
            m=re.search(r'\d{1,2} [A-Za-z]{3} \d{4}',date_evidence['quote'])
            if not m: raise ValueError('OCBC quote date missing')
            asof=datetime.strptime(m[0],'%d %b %Y').date().isoformat()
            unit_task,unit_evidence=metadata(p,record,'fx-annual',p.get_by_text(re.compile(r'^Rates quoted are on per annum basis')))
            channel_task,channel_evidence=metadata(p,record,'fx-online',p.get_by_text(re.compile(r'^Rates are only available from Mondays to Fridays',re.I)))
            published = set()
            for container in p.locator('.foreign-currency').all():
                heading=container.locator('h5').first
                label=heading.inner_text().strip(); cur=label.split(' - ',1)[0]
                published.add(cur)
                if cur not in REQUIRED-{'SGD'}:continue
                head_task,head_evidence=metadata(p,record,'fx-'+cur+'-currency',heading)
                rows,ids=table_tasks(p,record,'fx-'+cur,container.locator('table'))
                sections.append(dict(id=prefix+cur,bank='OCBC',currency=cur,product_id='ocbc-fx-online-board',layout='ocbc-fx',rows=rows,
                    task_ids=ids+[head_task,date_task,unit_task,channel_task,minimum_task],page_id=record['id'],rate_basis='annual_nominal',
                    valid_from=asof,minimum='50000' if cur=='HKD' else '5000',basis_evidence=[minimum_evidence,head_evidence,date_evidence,unit_evidence,channel_evidence]))
                print('OCBC',cur,'captured',flush=True)
            finish(p,record)
            captured = {s['currency'] for s in sections}
            expected = {'SGD'} | (published & REQUIRED)
            if captured != expected or len(sections) != len(expected):
                raise ValueError('OCBC published currencies incomplete')
            for cur in sorted(REQUIRED - captured):
                coverage.append(dict(bank='OCBC',currency=cur,product_id='ocbc-fx-online-board',
                    reason=f'官网完整页面 {asof} 未列出此币种；本轮未取得报价，未补造数值',
                    numeric_insertion=False,source=record['url'],source_date=asof,
                    published_currencies=sorted(published)))
        finally:browser.close()
    run=dict(id=out.name,as_of=today,bank_dates={'OCBC':today},pages=pages,sections=sections,tasks=tasks,
             errors=[],coverage=coverage,evidence_hash=digest(pages),task_hash=digest(tasks),demo=False,registered_links=registered)
    save(out/'run.json',run); evidence_index(pages,ev)
    print('Captured',len(sections),'sections',len(tasks),'local verification tasks',flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--out',required=True); a.add_argument('--links',default='../利率链接.xlsx'); x=a.parse_args();capture(x.out,x.links)

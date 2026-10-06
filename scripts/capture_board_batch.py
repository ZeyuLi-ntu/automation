"""Single fetch per multi-currency source; archive literal HTML, grids and crops."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,re,hashlib
from playwright.sync_api import sync_playwright
from market_rates.common import save,digest
from market_rates.link_registry import entries
from market_rates.pipeline import evidence_index
from market_rates.workbook_policy import currency_in_scope

GRID='''t=>{const g=[];[...t.rows].forEach((r,i)=>{g[i]??=[];let j=0;[...r.cells].forEach(c=>{while(g[i][j]!==undefined)j++;for(let x=0;x<c.rowSpan;x++){g[i+x]??=[];for(let y=0;y<c.colSpan;y++)g[i+x][j+y]=c.innerText.trim()}j+=c.colSpan})});return g}'''

def capture(out):
    out=Path(out)
    if out.exists():raise ValueError('New capture directory required')
    ev=out/'evidence';ev.mkdir(parents=True);sources=entries('../利率链接.xlsx');pages=[];packets=[]
    def url(bank,hint):
        rows=[r for r in sources if r['bank']==bank and r['currency_hint']==hint and r['rate_type']=='board' and r['url']]
        if len(rows)!=1:raise ValueError('Source ambiguity')
        return rows[0]['url']
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True);ctx=b.new_context(viewport={'width':1440,'height':1800},locale='en-SG',device_scale_factor=1.5)
        def open_page(u,label):
            from urllib.parse import urlsplit
            host=urlsplit(u).hostname
            if host not in ['www.hlbank.com.sg','www.bankofchina.com']:raise ValueError('Unexpected bank host')
            p=ctx.new_page();p.route('**/*',lambda r:r.abort() if r.request.is_navigation_request() and urlsplit(r.request.url).hostname!=host else r.continue_())
            response=p.goto(u,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS);p.wait_for_timeout(PAGE_SETTLE_MS)
            if not response or response.status!=200:raise ValueError('Source unavailable')
            (ev/(label+'.html')).write_text(p.content(),encoding='utf8');return p
        def record(p,bank,cur,label,text,images,grid=None):
            (ev/(label+'.txt')).write_text(text,encoding='utf8')
            pages.append(dict(id=label,bank=bank,currency=cur,rate_type='board',url=p.url,text=text,images=images,grid=grid or [],
                ok=True,complete=True,product_ids=[bank.lower()+'-'+cur.lower()+'-board'],captured_at=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(text.encode()).hexdigest(),image_hashes={n:hashlib.sha256((ev/n).read_bytes()).hexdigest() for n in images}))
            return label
        def shot(region,name):region.screenshot(path=str(ev/name),animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS);return name
        try:
            h=open_page(url('HLB','SGD'),'hlb-rate-source');product=open_page(url('HLB','others'),'hlb-fx-product')
            eligible=product.get_by_text('Eligibility',exact=True).locator('..');mt=product.locator('table').filter(has_text='Minimum placement amount')
            min_grid=mt.evaluate(GRID);shared=[shot(eligible,'hlb-fx-eligibility.png'),shot(mt,'hlb-fx-minimums.png')]
            currencies=h.locator('.fd-dropdown select option').evaluate_all('xs=>xs.map(x=>x.value).filter(Boolean)')
            save(out/'hlb-currency-inventory.json',currencies)
            for cur in currencies:
                if not currency_in_scope(cur):continue
                if cur in ['SGD','USD']:continue # Already qualified pilot evidence is retained with its original date.
                h.locator('.fd-dropdown select').select_option(cur);h.wait_for_timeout(PAGE_SETTLE_MS)
                table=h.locator(f'table[data-for-currency="{cur}"]');region=h.locator('.rate-tables').locator('..');grid=table.evaluate(GRID)
                for attempt in range(20):
                    if float(table.evaluate('e=>getComputedStyle(e).opacity'))>=.99:break
                    h.wait_for_timeout(SCROLL_SETTLE_MS)
                label='hlb-'+cur.lower();rateid=record(h,'HLB',cur,label+'-rates',region.inner_text(),[shot(region,label+'-rates.png')],grid)
                termid=record(product,'HLB',cur,label+'-terms',eligible.inner_text()+'\n'+mt.inner_text(),shared,min_grid)
                packets.append(dict(bank='HLB',currency=cur,layout='vertical',pages=[rateid,termid]))
            h.close();product.close()
            index=open_page(url('BOC','others'),'boc-index')
            links=index.locator('a[href]').evaluate_all('xs=>xs.map(x=>({text:x.innerText.trim(),url:x.href}))')
            from market_rates.boc_discovery import latest_board_announcement
            latest,board=latest_board_announcement(links,datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d'))
            save(out/'boc-discovery.json',dict(index=index.url,candidates=board,selected=latest));index.close()
            p=open_page(latest['url'],'boc-board-source');table=p.locator('.trs_editor_view > table').filter(has_text='年利率').first
            if table.count()!=1:raise ValueError('BOC table missing')
            grid=table.evaluate(GRID);trs=table.locator('tr');heads=grid[:2]
            # Header crop retains the actual date above the table and both tenure rows.
            box=table.bounding_box();second=trs.nth(1).bounding_box();header='boc-header.png'
            p.screenshot(path=str(ev/header),clip={'x':box['x'],'y':max(0,box['y']-70),'width':box['width'],'height':second['y']+second['height']-max(0,box['y']-70)},animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS)
            footer=p.locator('p').filter(has_text='注：以上利率仅供参考').first;footername=shot(footer,'boc-footer.png');footertext=footer.inner_text()
            terms_url=p.get_by_text('定期账户',exact=True).get_attribute('href');terms=open_page(terms_url,'boc-account')
            mintable=terms.locator('.TRS_Editor table').filter(has_text='起存金额');minimum_grid=mintable.evaluate(GRID);minimum_img=shot(mintable,'boc-account-minimums.png')
            effective=latest['date'];effective=effective[:4]+'-'+effective[4:6]+'-'+effective[6:]
            groups={}
            for i,r in enumerate(grid[2:],2):
                m=re.search(r'\(([A-Z]{3})\)',r[0])
                if not m:raise ValueError('Unrecognized currency row')
                original=m[1];cur='CNY' if original=='RMB' else original;groups.setdefault(cur,[]).append((i,r))
            for cur,rows in groups.items():
                if not currency_in_scope(cur):continue
                # Exact pixels of the original bank table, not a reconstructed table.
                p.evaluate('window.scrollTo(0,0)');a=trs.nth(rows[0][0]).bounding_box();z=trs.nth(rows[-1][0]).bounding_box();name='boc-'+cur.lower()+'.png'
                p.screenshot(path=str(ev/name),clip={'x':box['x'],'y':a['y'],'width':box['width'],'height':z['y']+z['height']-a['y']},animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS)
                text=effective+'\n'+'\n'.join('\t'.join(r) for r in heads+[r for _,r in rows])+'\n'+footertext
                rateid=record(p,'BOC',cur,'boc-'+cur.lower()+'-rates',text,[header,name,footername],heads+[r for _,r in rows])
                termid=record(terms,'BOC',cur,'boc-'+cur.lower()+'-terms',mintable.inner_text(),[minimum_img],minimum_grid)
                packets.append(dict(bank='BOC',currency=cur,layout='horizontal',pages=[rateid,termid]))
            p.close();terms.close()
        finally:b.close()
    now=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    run=dict(id=out.name,as_of=now,pages=pages,packets=packets,bank_dates={b:now for b in ['BOC','HLB']},evidence_hash=digest(pages),errors=[],demo=False,pilot={'no_publication':True,'scope':'BOC/HLB multi-currency board expansion'},rate_scopes=[dict(currency=c,rate_type='board') for c in sorted({x['currency'] for x in packets})])
    save(out/'run.json',run);save(out/'link-snapshot.json',sources);evidence_index(pages,ev)
    print({'packets':len(packets),'pages':len(pages),'currencies':sorted({x['currency'] for x in packets})},flush=True)
    return run
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);capture(a.parse_args().out)

"""Remaining modal, mixed product and PDF sources for the wide bank batch."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse,hashlib,re,shutil
from pathlib import Path
from datetime import datetime,timezone,timedelta
from playwright.sync_api import sync_playwright
import pymupdf
from market_rates.common import load,save,digest
from market_rates.pipeline import evidence_index
from scripts.capture_board_wave import PHYSICAL,shot

def capture(discovery,out,modern_sources=False,icbc_hlf_modern=False):
    discovery=Path(discovery);out=Path(out);ev=out/'evidence';ev.mkdir(parents=True,exist_ok=False);pages=[];sections=[];tasks=[];errors=[]
    now=datetime.now(timezone.utc).isoformat()
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True,args=['--disable-http2'])
        try:
            for key,bank,indices in [('CITI-D18','CITI',[7]),('ICBC-D41','ICBC',[90]),('CIMB-D12','CIMB',range(7))]:
                if modern_sources and bank=='CIMB':continue
                if icbc_hlf_modern and bank=='ICBC':continue
                p=b.new_page(viewport={'width':1440,'height':1600},device_scale_factor=1.5);src=load(discovery/key/'source.json')
                try:
                    r=p.goto(src['url'],wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                    if not r or r.status!=200:raise ValueError('Source unavailable')
                    p.wait_for_timeout(PAGE_SETTLE_MS)
                    if bank=='CITI':p.get_by_text('Click here to view the rates',exact=True).click(timeout=CONTENT_TIMEOUT_MS);p.wait_for_timeout(PAGE_SETTLE_MS)
                    text=p.locator('body').inner_text();images=[]
                    for i in indices:
                        table=p.locator('table').nth(i)
                        if not table.is_visible():raise ValueError('Hidden board table')
                        rows=table.evaluate(PHYSICAL);tid=bank.lower()+'-board-'+str(i);name=tid+'.png'
                        shot(p,table,ev/name);images.append(name)
                        tasks.append(dict(id=tid,bank=bank,kind='grid',expected=rows,images=[name],page_id=key))
                        sections.append(dict(id=tid,bank=bank,currency='FX' if bank=='CIMB' else 'SGD',product_id=tid,table=i,rows=rows,task_ids=[tid],page_id=key))
                    (ev/(key+'.html')).write_text(p.content(),encoding='utf8');(ev/(key+'.txt')).write_text(text,encoding='utf8')
                    pages.append(dict(id=key,bank=bank,currency='multi',rate_type='board',url=p.url,text=text,images=images,ok=True,complete=True,captured_at=now,sha256=hashlib.sha256(text.encode()).hexdigest()))
                    print(bank,'captured',flush=True)
                except Exception as exc:errors.append(dict(bank=bank,error=str(exc)));print(bank,'ERROR',str(exc)[:120],flush=True)
                finally:p.close()
        finally:b.close()
    try:
        src=load(discovery/'RHB-D56/source.json');doc=pymupdf.open(discovery/'RHB-D56/source.pdf');pg=doc[0];grid=pg.find_tables().tables[0].extract()
        rows=[[c for c in row if c] for row in grid[1:4]]
        # PDF coordinates derive from the printed header/rows and conditions.
        regions=[('rhb-sgd-board',pymupdf.Rect(60,180,700,241),'grid',rows),('rhb-sgd-context',pymupdf.Rect(60,132,700,181),'text',None),('rhb-sgd-terms',pymupdf.Rect(60,240,730,270),'text',None)]
        images=[]
        for tid,rect,kind,expected in regions:
            name=tid+'.png';scale=3 if tid=='rhb-sgd-context' else 2;pg.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=rect).save(str(ev/name));images.append(name)
            value=expected if expected is not None else pg.get_text(clip=rect,sort=True).strip()
            tasks.append(dict(id=tid,bank='RHB',kind=kind,expected=value,images=[name],page_id='RHB-D56'))
        shutil.copy2(discovery/'RHB-D56/source.pdf',ev/'rhb-source.pdf');text=pg.get_text()
        pages.append(dict(id='RHB-D56',bank='RHB',currency='SGD',rate_type='board',url=src['url'],text=text,images=images,ok=True,complete=True,captured_at=now,sha256=hashlib.sha256(text.encode()).hexdigest()))
        sections.append(dict(id='rhb-sgd-board',bank='RHB',currency='SGD',product_id='rhb-sgd-board',table=0,rows=rows,task_ids=[x[0] for x in regions],page_id='RHB-D56'))
    except Exception as exc:errors.append(dict(bank='RHB',error=str(exc)))
    for page in pages:page['image_hashes']={n:hashlib.sha256((ev/n).read_bytes()).hexdigest() for n in page['images']}
    for task in tasks:task['image_hashes']={n:hashlib.sha256((ev/n).read_bytes()).hexdigest() for n in task['images']}
    today=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    run=dict(id=out.name,as_of=today,bank_dates={p['bank']:datetime.fromisoformat(p['captured_at']).astimezone(timezone(timedelta(hours=8))).date().isoformat() for p in pages},pages=pages,sections=sections,tasks=tasks,errors=errors,evidence_hash=digest(pages),task_hash=digest(tasks),demo=False)
    save(out/'run.json',run);evidence_index(pages,ev);print('Sections',len(sections),'tasks',len(tasks),'errors',errors,flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--discovery',required=True);a.add_argument('--out',required=True);a.add_argument('--modern-sources',action='store_true');a.add_argument('--icbc-hlf-modern',action='store_true');args=a.parse_args();capture(args.discovery,args.out,args.modern_sources,args.icbc_hlf_modern)

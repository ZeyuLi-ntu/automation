"""Recapture failed tables as smaller original-pixel tasks; never change values."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse,shutil,hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright
from market_rates.common import load,save,digest
from scripts.capture_board_wave import PHYSICAL,shot
from market_rates.board_batch import compact

def repair(source,out):
    source=Path(source);out=Path(out);shutil.copytree(source,out);run=load(out/'run.json')
    proof=load(source/'wave-checks.json');failed={c['task'] for c in proof['checks'] if not c['passed']};old={t['id']:t for t in run['tasks']};tasks=[t for t in run['tasks'] if t['id'] not in failed]
    pages={p['id']:p for p in run['pages']};ev=out/'evidence'
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--disable-http2'])
        try:
            for section in run['sections']:
                tid=section['id']
                if tid not in failed:continue
                p=browser.new_page(viewport={'width':1440,'height':1600},device_scale_factor=2);page=pages[section['page_id']]
                try:
                    p.goto(page['url'],wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS);p.wait_for_timeout(PAGE_SETTLE_MS)
                    if section['bank']=='CITI':p.get_by_text('Click here to view the rates',exact=True).click(timeout=CONTENT_TIMEOUT_MS)
                    table=p.locator('table').nth(section['table']);table.scroll_into_view_if_needed();p.wait_for_timeout(PAGE_SETTLE_MS)
                    rows=table.evaluate(PHYSICAL);expected=section['rows'];caption=table.locator('caption').inner_text() if table.locator('caption').count() else ''
                    if caption.strip():rows=[[caption.strip()]]+rows
                    canon=lambda rows:[[compact(v) for v in row] for row in rows]
                    if canon(rows)!=canon(expected):
                        save(out/('recapture-change-'+tid+'.json'),dict(expected=expected,actual=rows))
                        raise ValueError('Source changed at '+tid+'; failed task cannot use a different table')
                    ids=[];newrows=[]
                    locators=([table.locator('caption')] if caption.strip() else [])+table.locator('tr').all()
                    for n,loc in enumerate(locators):
                        cells=[loc.inner_text().strip()] if caption.strip() and n==0 else loc.evaluate("r=>[...r.cells].map(c=>c.innerText.trim()).filter(Boolean)")
                        if not cells:continue
                        ident=tid+'-row-'+str(n);name=ident+'.png';shot(p,loc,ev/name);newrows.append(cells);ids.append(ident)
                        tasks.append(dict(id=ident,bank=section['bank'],kind='grid',expected=[cells],images=[name],page_id=section['page_id'],image_hashes={name:hashlib.sha256((ev/name).read_bytes()).hexdigest()}))
                        page['images'].append(name);page['image_hashes'][name]=hashlib.sha256((ev/name).read_bytes()).hexdigest()
                    if canon(newrows)!=canon(expected):raise ValueError('Row evidence coverage differs')
                    section['task_ids']=[i for i in section['task_ids'] if i!=tid]+ids
                    print('Recaptured',tid,len(ids),'rows',flush=True)
                finally:p.close()
        finally:browser.close()
    run.update(id=out.name,tasks=tasks,task_hash=digest(tasks),evidence_hash=digest(run['pages']),repair_source=str(source.resolve()));save(out/'run.json',run)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--run',required=True);a.add_argument('--out',required=True);args=a.parse_args();repair(args.run,args.out)

"""Live SPA tables, linked HSBC PDFs, and bounded original-pixel table tiles."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse,hashlib,re,shutil
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pymupdf
from playwright.sync_api import sync_playwright
from market_rates.common import load,save,digest
from market_rates.pipeline import evidence_index
from scripts.capture_board_wave import PHYSICAL,shot
from urllib.parse import urlsplit

CIMB_HEADINGS=['US Dollar','Sterling Pound','Australian Dollar','New Zealand Dollar','Euro','Canadian Dollar','Renminbi (Offshore)']
SCB_HEADINGS=['U.S. DOLLARS','STERLING POUNDS','AUSTRALIAN DOLLARS','NEW ZEALAND DOLLARS','EURO','CANADIAN DOLLARS','HONGKONG DOLLARS','CHINESE REMINBI (CNH)']

def source_confirmation(bank,cur,url):
    rules=load(Path(__file__).resolve().parents[1]/'config/board-source-confirmations.json')['rules'];u=urlsplit(url)
    return next((r for r in rules if r['bank']==bank and r['scope']==cur and r['host']==u.hostname and r['path']==u.path),None)

def effective_date(text):
    match=re.search(r'Effective from:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})',text)
    if not match:raise ValueError('Maybank effective date missing')
    return datetime.strptime(match[1],'%d %B %Y').date().isoformat()

def attach_hsbc_audiences(run,root):
    """Verify the PDF audience heading, in addition to each currency/date."""
    ev=Path(root)/'evidence'
    for page in run['pages']:
        if page['bank']!='HSBC' or not page['url'].split('?')[0].endswith('.pdf'):continue
        suffix=page['id'].rsplit('-',1)[1]
        source=ev/(page['id'].rsplit('hsbc-',1)[0]+'fcy-time-deposits-'+suffix+'.pdf')
        doc=pymupdf.open(source);pg=doc[0]
        blocks=[b for b in pg.get_text('blocks') if 'Foreign Currency Time Deposit Rates' in b[4]]
        if len(blocks)!=1:raise ValueError('HSBC audience heading missing')
        block=blocks[0];expected=block[4].strip();audience='Personal Banking' if suffix=='pb' else 'Premier'
        if audience not in expected:raise ValueError('HSBC PDF audience does not match the link')
        fn=page['id']+'-audience.png';rect=pymupdf.Rect(block[:4])+(-2,-2,2,2)
        pg.get_pixmap(matrix=pymupdf.Matrix(2,2),clip=rect).save(str(ev/fn));sha=hashlib.sha256((ev/fn).read_bytes()).hexdigest()
        tid=page['id']+'-audience';run['tasks'].append(dict(id=tid,bank='HSBC',kind='text',expected=expected,images=[fn],image_hashes={fn:sha},page_id=page['id']))
        page['images'].append(fn);page['image_hashes'][fn]=sha
        for section in run['sections']:
            if section['page_id']==page['id']:section['task_ids'].append(tid)
        run.setdefault('source_file_hashes',{})[source.name]=hashlib.sha256(source.read_bytes()).hexdigest()

def capture(discovery,out,banks=None):
    discovery=Path(discovery);out=Path(out);ev=out/'evidence';ev.mkdir(parents=True,exist_ok=False)
    pages=[];sections=[];tasks=[];now=datetime.now(timezone.utc).isoformat();today=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    prefix=out.name+'-'
    def task(tid,bank,rows,image_names,pid,**extra):
        t=dict(id=prefix+tid,bank=bank,kind='grid',expected=rows,images=image_names,page_id=pid,**extra)
        t['image_hashes']={n:hashlib.sha256((ev/n).read_bytes()).hexdigest() for n in image_names};tasks.append(t);return t['id']
    def page_record(pid,bank,url,text,images):
        pages.append(dict(id=pid,bank=bank,currency='multi',rate_type='board',url=url,text=text,images=images,ok=True,complete=True,captured_at=now,sha256=hashlib.sha256(text.encode()).hexdigest(),image_hashes={n:hashlib.sha256((ev/n).read_bytes()).hexdigest() for n in images}))
    specs=[('BEA-D3','BEA','FX',[0,1]),('BEA-D5','BEA','SGD',[0]),('Maybank-D46','Maybank','SGD',[3]),('SCB-D66','SCB','FX',list(range(8))),('CIMB-D12','CIMB','FX',list(range(7)))]
    if banks:specs=[s for s in specs if s[1] in banks]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--disable-http2'])
        ctx=browser.new_context(viewport={'width':1440,'height':1600},device_scale_factor=2,locale='en-SG')
        try:
            for key,bank,cur,indices in specs:
                src=load(discovery/key/'source.json');p=ctx.new_page();pid=prefix+key
                try:
                    response=p.goto(src.get('final_url',src['url']),wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
                    if not response or response.status!=200:raise ValueError('Source unavailable '+key)
                    p.locator('table').first.wait_for(state='visible',timeout=CONTENT_TIMEOUT_MS);p.wait_for_timeout(PAGE_SETTLE_MS)
                    if bank=='SCB':
                        # The delayed consent banner has children with explicit
                        # visibility, so hiding its parent visibility is insufficient.
                        # Hide only this observed UI widget; never rate content.
                        p.add_style_tag(content='#onetrust-consent-sdk { display:none !important; }')
                    text=p.locator('body').inner_text();images=[]
                    (ev/(pid+'.html')).write_text(p.content(),encoding='utf8');(ev/(pid+'.txt')).write_text(text,encoding='utf8')
                    for index in indices:
                        table=p.locator('table').nth(index);table.scroll_into_view_if_needed();p.wait_for_timeout(PAGE_SETTLE_MS)
                        rows=table.evaluate(PHYSICAL);original=next(t['rows'] for t in src['tables'] if t['index']==index)
                        if rows!=original:raise ValueError('Source changed since discovery: '+key)
                        name=('maybank-sgd-board' if bank=='Maybank' else 'bea-'+('sgd' if cur=='SGD' else 'fx-'+('board' if index==0 else 'tier')) if bank=='BEA' else bank.lower()+'-fx-'+str(index))
                        kept=[];ids=[];locs=[];batch=[];batch_rows=[]
                        def flush():
                            if not batch:return
                            if bank=='SCB' and len(batch)==1 and len(batch_rows[0])>4:
                                cells=batch[0].locator(':scope > th, :scope > td').all()
                                for start in range(0,len(cells),4):
                                    group=cells[start:start+4];boxes=[c.bounding_box() for c in group];fn=prefix+name+'-'+str(len(ids))+'.png'
                                    x=min(b['x'] for b in boxes);y=min(b['y'] for b in boxes);right=max(b['x']+b['width'] for b in boxes);bottom=max(b['y']+b['height'] for b in boxes)
                                    p.screenshot(path=str(ev/fn),clip=dict(x=x,y=y,width=right-x,height=bottom-y),animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS)
                                    ids.append(task(name+'-'+str(len(ids)),bank,[batch_rows[0][start:start+4]],[fn],pid,comparison_profile='scb-range-separator'));images.append(fn)
                                batch.clear();batch_rows.clear();return
                            # Original document pixels, spanning at most 3 physical rows.
                            boxes=[x.bounding_box() for x in batch];x=min(b['x'] for b in boxes);y=min(b['y'] for b in boxes);right=max(b['x']+b['width'] for b in boxes);bottom=max(b['y']+b['height'] for b in boxes)
                            fn=prefix+name+'-'+str(len(ids))+'.png'
                            p.screenshot(path=str(ev/fn),clip=dict(x=x,y=y,width=right-x,height=bottom-y),animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS)
                            ids.append(task(name+'-'+str(len(ids)),bank,list(batch_rows),[fn],pid,comparison_profile='scb-range-separator' if bank=='SCB' else 'literal'))
                            if all(len(row)==1 for row in batch_rows):tasks[-1].update(kind='text',expected='\n'.join(row[0] for row in batch_rows))
                            images.append(fn);batch.clear();batch_rows.clear()
                        # Keep floating navigation/cookie layers outside the table hidden during tiles.
                        table.evaluate("e=>{window.__repairFloating=[...document.querySelectorAll('*')].filter(x=>x!==e&&!x.contains(e)&&!e.contains(x)&&['fixed','sticky'].includes(getComputedStyle(x).position)).map(x=>[x,x.style.visibility]);window.__repairFloating.forEach(([x])=>x.style.visibility='hidden')}")
                        for tr in table.locator('tr').all():
                            cells=tr.evaluate("r=>[...r.cells].map(c=>c.innerText.trim()).filter(Boolean)")
                            if not cells:continue
                            if 'JPY' in cells or any('Japanese Yen' in c for c in cells):flush();continue
                            if len(batch)==3:flush()
                            kept.append(cells);batch.append(tr);batch_rows.append(cells)
                        flush();p.evaluate("()=>window.__repairFloating.forEach(([x,v])=>x.style.visibility=v)")
                        section=dict(id=prefix+name,bank=bank,currency=cur,product_id=name,table=index,rows=kept,task_ids=ids,page_id=pid)
                        def metadata(label,loc):
                            fn=prefix+name+'-'+label+'.png';shot(p,loc,ev/fn);expected=loc.inner_text().strip()
                            tid=task(name+'-'+label,bank,[[expected]],[fn],pid);tasks[-1].update(kind='text',expected=expected);ids.append(tid);images.append(fn);return expected
                        if bank=='BEA':
                            section['layout']='bea-fx' if cur=='FX' else 'bea-sgd';section['rate_basis']='annual_nominal'
                            date_loc=p.get_by_text(re.compile(r'^\(As at ')).filter(visible=True).first
                            dt=metadata('date',date_loc);m=re.search(r'\d{2}-[A-Z]{3}-\d{4}',dt);section['valid_from']=datetime.strptime(m[0],'%d-%b-%Y').date().isoformat()
                            if cur=='FX':
                                metadata('title',p.get_by_text('Board Rates' if index==0 else 'Tier Rates',exact=True).filter(visible=True).first)
                                metadata('limit',p.get_by_text('For fixed deposit amount of SGD500,000 equivalent or over, please contact us for the applicable prevailing interest rate.',exact=True).filter(visible=True).first)
                        if bank=='Maybank':section['valid_from']=effective_date(metadata('date',p.locator('table').nth(index+1)))
                        if bank=='CIMB':
                            heading=table.locator('xpath=preceding::h3[1]')
                            label=metadata('currency',heading)
                            if label!=CIMB_HEADINGS[index]:raise ValueError('CIMB currency order changed; review source mapping')
                            section['amount_mode']='quoted_point'
                        if bank=='SCB' and re.sub(r'\s+',' ',rows[0][0])!=SCB_HEADINGS[index]:raise ValueError('SCB currency order changed; review source mapping')
                        confirmation=source_confirmation(bank,cur,p.url)
                        if confirmation:section.update(rate_basis=confirmation['rate_basis'],unit_confirmation=confirmation)
                        sections.append(section)
                    page_record(pid,bank,p.url,text,images);print(bank,'HTML tables captured',flush=True)
                finally:p.close()
        finally:browser.close()
    hsbc=load(discovery/'HSBC-D36/source.json') if not banks or 'HSBC' in banks else None
    for audience,suffix in ([('personal','pb')] if hsbc else []):
        filename='fcy-time-deposits-'+suffix+'.pdf';source=discovery/'HSBC-D36'/filename;dest=ev/(prefix+filename);shutil.copy2(source,dest)
        url=next(l['url'] for l in hsbc['links'] if 'Foreign Currency Time Deposit rates' in l['text'] and ('Personal Banking' if suffix=='pb' else 'Premier') in l['text'] and l['url'].split('?')[0].endswith('.pdf'));doc=pymupdf.open(source);pid=prefix+'hsbc-'+suffix;images=[];active=None
        for pi,pg in enumerate(doc):
            for ti,table in enumerate(pg.find_tables().tables):
                rows=[[c.strip() for c in row if c and c.strip()] for row in table.extract()];rows=[r for r in rows if r]
                if not rows:continue
                header=re.search(r'\b(USD|GBP|JPY|CAD|CHF|NZD|AUD|HKD|EUR|CNY)\b',rows[0][0])
                is_header=len(rows[0])==1 and header
                if is_header:
                    cur=header[1]
                    context=pg.get_text(clip=pymupdf.Rect(table.bbox[0],max(0,table.bbox[1]-45),table.bbox[2],table.bbox[1]))
                    dates=re.findall(r'\d{4}-\d{2}-\d{2}',context)
                    if not dates:raise ValueError('HSBC table date missing')
                    active=None if cur=='JPY' else dict(id=prefix+'hsbc-'+suffix+'-'+cur,bank='HSBC',currency=cur,product_id='hsbc-fx-'+audience+'-board',table=ti,layout='hsbc-fx-pdf',audience=audience,source_date=dates[-1],rows=[],task_ids=[],page_id=pid)
                    if active:sections.append(active)
                if active is None:continue
                if not is_header and not rows[0][0].startswith(active['currency']):raise ValueError('Unexpected PDF continuation')
                name=prefix+'hsbc-'+suffix+'-p'+str(pi+1)+'-t'+str(ti)+'.png';rect=pymupdf.Rect(table.bbox)
                physical=[(r,[c.strip() for c in values if c and c.strip()]) for r,values in zip(table.rows,table.extract())];physical=[x for x in physical if x[1]]
                groups=[]
                if is_header:groups.extend([[physical[0]],[physical[1]]]);physical=physical[2:]
                groups.extend([row] for row in physical)
                for gi,group in enumerate(groups):
                    clip=pymupdf.Rect(rect.x0,group[0][0].bbox[1],rect.x1,group[-1][0].bbox[3]);fn=name.replace('.png','-part'+str(gi)+'.png')
                    pg.get_pixmap(matrix=pymupdf.Matrix(2,2),clip=clip).save(str(ev/fn));images.append(fn)
                    active['task_ids'].append(task('hsbc-'+suffix+'-p'+str(pi+1)+'-t'+str(ti)+'-part'+str(gi),'HSBC',[x[1] for x in group],[fn],pid))
                active['rows']+=rows
                if is_header:
                    date_words=[w for w in pg.get_text('words',clip=pymupdf.Rect(rect.x0,rect.y0-45,rect.x1,rect.y0)) if re.fullmatch(r'\d{4}-\d{2}-\d{2}',w[4])]
                    if not date_words:raise ValueError('HSBC printed date cell missing')
                    word=max(date_words,key=lambda w:w[1]);dr=pymupdf.Rect(word[:4])+(-2,-2,2,2);date_text=word[4];fn=name.replace('.png','-date.png')
                    pg.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=dr).save(str(ev/fn));images.append(fn)
                    # Text tasks verify the distinct date printed for this currency.
                    tid=task('hsbc-'+suffix+'-'+active['currency']+'-date','HSBC',[[date_text]],[fn],pid)
                    tasks[-1].update(kind='text',expected=date_text);active['task_ids'].append(tid)
        page_record(pid,'HSBC',url,'\n'.join(p.get_text() for p in doc),images);print('HSBC',audience,'PDF tables captured',flush=True)
    run=dict(id=out.name,as_of=today,bank_dates={p['bank']:today for p in pages},pages=pages,sections=sections,tasks=tasks,errors=[],evidence_hash=digest(pages),task_hash=digest(tasks),demo=False)
    attach_hsbc_audiences(run,out);run.update(evidence_hash=digest(pages),task_hash=digest(tasks))
    save(out/'run.json',run);evidence_index(pages,ev);print('Captured',len(sections),'sections',len(tasks),'tasks',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--discovery',required=True);p.add_argument('--out',required=True);p.add_argument('--banks');a=p.parse_args();capture(a.discovery,a.out,a.banks.split(',') if a.banks else None)

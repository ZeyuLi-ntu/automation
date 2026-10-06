"""Capture all remaining Bank List board sources as small original-pixel tiles."""
import argparse,hashlib,re,traceback
from datetime import datetime,timezone
from pathlib import Path
import pymupdf
from playwright.sync_api import sync_playwright
from market_rates.board_capture import BoardCapture
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS,CONTENT_TIMEOUT_MS,PAGE_SETTLE_MS
from market_rates.common import save
from market_rates.link_registry import entries
from scripts.capture_board_wave import PHYSICAL

FX={'USD','AUD','NZD','CAD','HKD','EUR','GBP','CNY','CNH'}
UOB_NAMES={'US DOLLAR':'USD','AUSTRALIAN DOLLAR':'AUD','BRITISH POUND':'GBP','CANADIAN DOLLAR':'CAD','EURO':'EUR','HONG KONG DOLLAR':'HKD','NEW ZEALAND DOLLAR':'NZD','CHINESE RENMINBI (OFFSHORE)':'CNH'}
CIMB='https://www.cimb.com.sg/en/personal/help-support/rates-charges/rates/sgd-fixed-deposit-rates.html'

def capture(root,banks):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);registry=entries('../利率链接.xlsx')
    def url(cell):return next(e['url'] for e in registry if e['cell']==cell and e['url'])
    failures=[]
    for bank in banks:
        if (root/bank/'run.json').exists():
            print(bank,'REUSED completed capture',flush=True);continue
        if (root/bank/'evidence').exists():
            # Preserve failed evidence when resuming; each retry gets a new archive.
            old=(root/bank).resolve();archive=(root/(bank+'-failed-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))).resolve()
            if old.parent!=root.resolve() or archive.parent!=root.resolve():raise ValueError('Invalid capture archive path')
            old.rename(archive)
        batch=BoardCapture(root/bank);batch.prefix=root.name+'-'+bank+'-'
        def section(key,cur,rows,ids,page,layout,**extra):
            batch.sections.append(dict(id=batch.prefix+key,bank=bank,currency=cur,rows=rows,task_ids=ids,page_id=page['id'],layout=layout,product_id=bank.lower()+'-'+cur.lower()+'-board',**extra))
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,args=['--disable-http2']);ctx=browser.new_context(viewport={'width':1700,'height':1700},device_scale_factor=2,locale='en-SG');ctx.set_default_timeout(CONTENT_TIMEOUT_MS)
            try:
                if bank=='DBS':
                    p,page=batch.open(ctx,bank,'fx',url('D21'))
                    p.wait_for_function("()=>[...document.querySelectorAll('table')].some(t=>t.innerText.includes('Amt(USD)')&&t.rows.length>2)",timeout=CONTENT_TIMEOUT_MS)
                    termids=[];evidence=[]
                    for name,pattern in [('minimum',r'^For Foreign Currency FD, the minimum amount'),('short-tenors',r'^Weekly tenors are available')]:
                        tid,e=batch.text(p,page,name,p.get_by_text(re.compile(pattern)).filter(visible=True).last);termids.append(tid);evidence.append(e)
                    date=p.get_by_text(re.compile(r'^Effective Date:')).filter(visible=True).first
                    did,de=batch.text(p,page,'effective-date',date);source_date=datetime.strptime(re.search(r'\d{2}/\d{2}/\d{4}',de['quote'])[0],'%d/%m/%Y').date().isoformat()
                    for table in p.locator('table').all():
                        if not table.is_visible():continue
                        rows=table.evaluate(PHYSICAL)
                        if not rows:continue
                        m=re.fullmatch(r'Amt\(([A-Z]{3})\)',rows[0][0])
                        if not m or m[1] not in FX-{'CNY','CNH'}:continue
                        cur=m[1];rows,ids=batch.table(p,page,cur,table,transposed=True)
                        section(cur,cur,rows,ids+termids+[did],page,'dbs-fx',source_date=source_date,valid_from=source_date,extra_evidence=evidence+[de])
                    batch.finish(p,page);p.close()
                elif bank=='UOB':
                    p,page=batch.open(ctx,bank,'fx',url('D76'));table=p.locator('table').filter(has_text='CHINESE RENMINBI').first
                    table.wait_for(state='visible',timeout=CONTENT_TIMEOUT_MS);grid=table.evaluate(PHYSICAL)
                    headers,hids=batch.table(p,page,'headers',table,[0]);extra=[];evidence=[]
                    for key,pattern in [('monthly-minimum',r'^For 1-12 month tenors'),('weekly-minimum',r'^For 1-2 week tenors'),('quote-date',r'^Rates as at')]:
                        tid,e=batch.text(p,page,key,p.get_by_text(re.compile(pattern)).filter(visible=True).last);extra.append(tid);evidence.append(e)
                    rawdate=re.search(r'\d{1,2} [A-Za-z]+ \d{4}',evidence[-1]['quote'])[0];date=datetime.strptime(rawdate,'%d %B %Y').date().isoformat()
                    for i,row in enumerate(grid):
                        if len(row)!=1 or row[0] not in UOB_NAMES:continue
                        cur=UOB_NAMES[row[0]];end=next((j for j in range(i+1,len(grid)) if len(grid[j])==1),len(grid))
                        if cur=='EUR':continue # Bank List does not request it; the source has only dashes.
                        rows,ids=batch.table(p,page,cur,table,range(i,end),group_size=1)
                        section(cur,cur,headers+rows,ids+hids+extra,page,'uob-fx',source_date=date,extra_evidence=evidence)
                    batch.finish(p,page);p.close()
                elif bank=='SBI':
                    p,page=batch.open(ctx,bank,'fx',url('D71'));p.get_by_text('Foreign Currencies',exact=True).filter(visible=True).first.click(timeout=CONTENT_TIMEOUT_MS);p.wait_for_timeout(PAGE_SETTLE_MS)
                    for cur in ['AUD','GBP']:
                        table=p.locator('table').filter(has_text=cur+' deposit rates').filter(visible=True).first
                        rows,ids=batch.table(p,page,cur,table)
                        date=datetime.strptime(re.search(r'\d{2}\.[A-Za-z]{3}\.\d{4}',rows[0][0])[0],'%d.%b.%Y').date().isoformat()
                        section(cur,cur,rows,ids,page,'sbi-fx',source_date=date,valid_from=date)
                    batch.finish(p,page);p.close()
                elif bank=='CIMB':
                    p,page=batch.open(ctx,bank,'sgd',CIMB)
                    boards=p.locator('table').filter(has_text='Board Rates').filter(visible=True)
                    if boards.count()!=2:raise ValueError('CIMB conventional and Islamic board tables required')
                    for index,table in enumerate(boards.all()):
                        key='sgd' if index==0 else 'sgd-islamic';rows,ids=batch.table(p,page,key,table)
                        title=p.get_by_text('CIMB SGD Islamic Fixed Deposit Rates' if index else 'CIMB SGD Fixed Deposit Rates',exact=True).filter(visible=True).last
                        tid,ev=batch.text(p,page,key+'-title',title)
                        note=p.get_by_text(re.compile(r'A minimum placement of S\$5,000 is required')).filter(visible=True).nth(index)
                        nid,ne=batch.text(p,page,key+'-minimum',note)
                        if '5,000' not in ne['quote']:raise ValueError('CIMB short tenor minimum changed')
                        section(key,'SGD',rows,ids+[tid,nid],page,'cimb-sgd',islamic=index==1,extra_evidence=[ev,ne])
                        batch.sections[-1]['product_id']='cimb-'+key+'-board'
                    batch.finish(p,page);p.close()
                elif bank=='HLB':
                    p,page=batch.open(ctx,bank,'hkd',url('D28'));p.locator('.fd-dropdown select').select_option('HKD');p.wait_for_timeout(PAGE_SETTLE_MS)
                    table=p.locator('table[data-for-currency="HKD"]');rows,ids=batch.table(p,page,'hkd',table)
                    loc=p.get_by_text(re.compile(r'^Effective Date:')).filter(visible=True).last
                    tid,ev=batch.text(p,page,'effective-date',loc);date=datetime.strptime(re.search(r'\d{1,2}-[A-Za-z]{3}-\d{4}',ev['quote'])[0],'%d-%b-%Y').date().isoformat()
                    section('hkd','HKD',rows,ids+[tid],page,'hlb-hkd',source_date=date,valid_from=date,extra_evidence=[ev]);batch.finish(p,page);p.close()
                elif bank=='RHB':
                    response=ctx.request.get(url('D56'),timeout=PAGE_LOAD_TIMEOUT_MS)
                    if not response.ok:raise ValueError('RHB PDF HTTP '+str(response.status))
                    blob=response.body();name=batch.prefix+'source.pdf';(batch.ev/name).write_bytes(blob)
                    doc=pymupdf.open(stream=blob,filetype='pdf')
                    for pi in [1,2]:
                        pg=doc[pi];tab=pg.find_tables().tables[0];grid=tab.extract();key='p'+str(pi+1)
                        page=dict(id=batch.prefix+key,bank=bank,currency='multi',rate_type='board',url=url('D56'),ok=True,complete=True,captured_at=datetime.now(timezone.utc).isoformat(),images=[],image_hashes={},text=pg.get_text());page['sha256']=hashlib.sha256(page['text'].encode()).hexdigest()
                        # Each source PDF row has its original boundaries, so no OCR layout guessing.
                        def task(index):
                            row=grid[index];fn=batch.prefix+key+'-r'+str(index)+'.png';rect=pymupdf.Rect(tab.rows[index].bbox)
                            if re.search(r'\([A-Z]{3}\)',row[0] or ''):
                                first=row[0].split()[0];words=[w for w in pg.get_text('words',clip=rect) if w[4]==first]
                                if len(words)!=1:raise ValueError('Currency name position ambiguous')
                                rect.x0=words[0][0]-2
                            pg.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=rect).save(batch.ev/fn)
                            # Currency label and every rate stay visible; original PDF retains flags.
                            return batch.task(page,key+'-r'+str(index),[[c for c in row if c]],fn,'grid')
                        headerids={};group=None
                        for i,row in enumerate(grid):
                            if i==0 or (len([v for v in row if v])==1 and re.search(r'\d.*(?:to|above| - )',row[0] or '')):
                                group=row[0];gid=task(i);continue
                            if row[0]=='Currency':headers=row;hid=task(i);continue
                            match=re.search(r'\(([A-Z]{3})\)',row[0] or '')
                            if not match or match[1] not in FX:continue
                            cur=match[1];rid=task(i);date=datetime.strptime(re.search(r'\d{2}-[A-Za-z]{3}-\d{2}',grid[0][0])[0],'%d-%b-%y').date().isoformat()
                            band=re.search(r'(Up to 99,999|100,000 to 499,999|500,000 - 999,999|1,000,000 & above)',group)[0]
                            section(key+'-'+str(i),cur,[headers,row],[gid,hid,rid],page,'rhb-fx',band=band,source_date=date)
                        batch.pages.append(page)
                    doc.close()
                else:raise ValueError(bank)
                if bank=='CIMB':
                    for task in batch.tasks:task['comparison_profile']='cimb-sgd-dollar-sign'
                batch.save();print(bank,'COMPLETE',flush=True)
            except Exception as exc:
                save(root/bank/'capture-error.json',dict(bank=bank,error=str(exc)));print(bank,'FAILED',str(exc)[:500],flush=True)
                failures.append(bank)
            finally:browser.close()
    if failures:raise ValueError('采集未完成：'+', '.join(failures)+'；重试会保留已完成银行和失败证据')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);a.add_argument('--banks',default='DBS,UOB,RHB,SBI,CIMB,HLB');x=a.parse_args();capture(x.out,x.banks.split(','))

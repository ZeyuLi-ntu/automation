"""Capture registered foreign-currency promotions and their eligibility evidence locally."""
import argparse,re,hashlib,shutil
from pathlib import Path
from datetime import datetime,timezone
import pymupdf
from playwright.sync_api import sync_playwright
from market_rates.board_capture import BoardCapture
from market_rates.browser_wait import CONTENT_TIMEOUT_MS,PAGE_SETTLE_MS,PAGE_LOAD_TIMEOUT_MS
from market_rates.common import load,save,digest
from market_rates.link_registry import entries
from scripts.capture_board_wave import PHYSICAL

def capture(out,banks):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);registry=entries('../利率链接.xlsx')
    def link(bank,cur='others'):return next(r['url'] for r in registry if r['bank']==bank and r['currency_hint']==cur and r['rate_type']=='promo' and r['url'])
    failures=[]
    for bank in banks:
        if (out/bank/'run.json').exists():print(bank,'captured already',flush=True);continue
        if (out/bank).exists():
            (out/bank).rename(out/(bank+'-failed-'+datetime.now().strftime('%H%M%S%f')))
        batch=BoardCapture(out/bank);batch.prefix=out.name+'-'+bank+'-'
        with sync_playwright() as pw:
            b=pw.chromium.launch(headless=True,args=['--disable-http2']);ctx=b.new_context(viewport={'width':1700,'height':1900},device_scale_factor=2,locale='en-SG');ctx.set_default_timeout(CONTENT_TIMEOUT_MS)
            try:
                def open_page(key,url):
                    p,page=batch.open(ctx,bank,key,url);page['rate_type']='promo';return p,page
                def txt(key,pattern):return batch.text(p,page,key,p.get_by_text(re.compile(pattern)).filter(visible=True).last)
                def section(key,rows,ids,extra=None,**kw):
                    batch.sections.append(dict(id=batch.prefix+key,bank=bank,currency=kw.pop('currency','multi'),product_id=bank.lower()+'-fx-'+key,layout='fx-promo-'+key,rows=rows,task_ids=ids,page_id=page['id'],extra_evidence=extra or [],**kw))
                def terms(name,pattern):
                    from urllib.parse import urlsplit
                    refs=p.locator('a[href]').evaluate_all('xs=>xs.map(x=>x.href)')
                    matches=list(dict.fromkeys(u.replace('http:','https:').split('#')[0] for u in refs if pattern in u and '.pdf' in u.lower()))
                    if len(matches)!=1:raise ValueError('Current official terms missing or ambiguous: '+name)
                    url=matches[0];host=urlsplit(p.url).hostname;target=urlsplit(url).hostname
                    if not (target==host or target.endswith('.'+host.removeprefix('www.'))):raise ValueError('Terms left the bank domain')
                    response=ctx.request.get(url,timeout=PAGE_LOAD_TIMEOUT_MS)
                    if not response.ok:raise ValueError('Terms HTTP '+str(response.status))
                    fn=batch.prefix+name+'.pdf';(batch.ev/fn).write_bytes(response.body())
                    with pymupdf.open(batch.ev/fn) as pdf:r=dict(url=url,text='\n'.join(pg.get_text() for pg in pdf))
                    doc=pymupdf.open(batch.ev/fn);ids=[];ev=[]
                    pdfpage=dict(id=batch.prefix+name,bank=bank,currency='multi',rate_type='promo',url=r['url'],ok=True,complete=True,captured_at=datetime.now(timezone.utc).isoformat(),images=[],image_hashes={},text=r['text'],sha256=hashlib.sha256(r['text'].encode()).hexdigest())
                    # Clauses that determine participation, amount, validity and channels.
                    for pi,pg in enumerate(doc):
                        for bi,block in enumerate(pg.get_text('blocks')):
                            text=block[4].strip()
                            if bank=='CITI' and 'All rates offered are promotional rates' in text:continue # Website verifies full rate grid; this PDF block cuts through its header.
                            if bank=='HSBC' and pi>0:continue # Eligibility is page 1; rates use complete website tables.
                            if not re.search(r'Promotion Period|Promotional Period|minimum|maximum|new or existing funds|Fresh Funds|Only personal|convert|conversion|USD 50,000|30,000|tenure under|from 01 September|from 3 August|no less than|existing DBS Personal',text,re.I):continue
                            if len(text.split())<15:continue # Fragmented PDF table captions are verified in the webpage table.
                            if len(text)>600:
                                lines=[l for bb in pg.get_text('dict')['blocks'] if bb.get('type')==0 for l in bb['lines'] if pymupdf.Rect(block[:4]).contains(pymupdf.Rect(l['bbox']))]
                                for start in range(0,len(lines),3):
                                    part=lines[start:start+3];literal='\n'.join(''.join(sp['text'] for sp in l['spans']) for l in part)
                                    if not literal.strip():continue
                                    rect=pymupdf.Rect(part[0]['bbox'])
                                    for l in part[1:]:rect|=pymupdf.Rect(l['bbox'])
                                    key=f'{name}-{pi}-{bi}-lines-{start}';image=batch.prefix+key+'.png'
                                    pg.get_pixmap(matrix=pymupdf.Matrix(2.3,2.3),clip=rect+(-1,-1,1,1)).save(batch.ev/image)
                                    ids.append(batch.task(pdfpage,key,literal,image,'text'));batch.tasks[-1]['comparison_profile']='promo-terms';ev.append(dict(page_id=pdfpage['id'],quote=literal,locator=key))
                                continue
                            key=name+'-'+str(pi)+'-'+str(bi);image=batch.prefix+key+'.png'
                            pg.get_pixmap(matrix=pymupdf.Matrix(2.3,2.3),clip=pymupdf.Rect(block[:4])+(-1,-1,1,1)).save(batch.ev/image)
                            ids.append(batch.task(pdfpage,key,text,image,'text'));batch.tasks[-1]['comparison_profile']='promo-terms';ev.append(dict(page_id=pdfpage['id'],quote=text,locator=key))
                    (batch.ev/(pdfpage['id']+'.txt')).write_text(r['text'],encoding='utf8');batch.pages.append(pdfpage);doc.close();return ids,ev
                if bank=='BEA':
                    p,page=open_page('tier',link(bank));p.locator('table').nth(1).wait_for(state='visible')
                    tid,te=txt('tier-heading',r'^Tier Rates$');table=p.locator('table').nth(1);grid=table.evaluate(PHYSICAL)
                    selected=[i for i,row in enumerate(grid) if i<2 or (len(row)>2 and row[1]!='JPY')]
                    rows,ids=batch.table(p,page,'tier',table,selected,group_size=1)
                    # A rowspan Currency cell is not part of the second physical header row.
                    cell=table.locator('tr').nth(1).locator(':scope > th, :scope > td').first
                    for task in batch.tasks:
                        if task['id']==batch.prefix+'tier-1':
                            cell.scroll_into_view_if_needed();p.evaluate('(dy)=>window.scrollBy(0,dy)',cell.bounding_box()['y']-180)
                            boxes=[c.bounding_box() for c in table.locator('tr').nth(1).locator(':scope > th, :scope > td').all()];left=min(c['x'] for c in boxes);top=min(c['y'] for c in boxes);right=max(c['x']+c['width'] for c in boxes);bottom=max(c['y']+c['height'] for c in boxes)
                            name=task['images'][0];p.screenshot(path=str(batch.ev/name),clip=dict(x=left,y=top,width=right-left,height=bottom-top),animations='disabled')
                            sha=hashlib.sha256((batch.ev/name).read_bytes()).hexdigest();task['image_hashes'][name]=sha;page['image_hashes'][name]=sha
                    nid,ne=txt('negotiation',r'^For fixed deposit amount of SGD500,000')
                    did,de=txt('source-date',r'As at \d+-[A-Za-z]+-\d{4}')
                    dt=re.search(r'\d+-[A-Za-z]+-\d{4}',de['quote'])[0]
                    section('tier',rows,ids+[tid,nid,did],[te,ne,de],source_category='Tier Rates',source_date=datetime.strptime(dt,'%d-%b-%Y').date().isoformat())
                    batch.finish(p,page);p.close()
                elif bank=='CIMB':
                    p,page=open_page('online',link(bank));table=p.locator('table').filter(has_text='Online Rates').first;rows,ids=batch.table(p,page,'online',table,group_size=1)
                    tid,te=txt('online-start',r'^From \d{1,2} [A-Za-z]+ 20\d{2}');mid,me=txt('online-minimum',r'^\*Online interest rates apply')
                    tids,ev=terms('online-terms','tnc-fcfd');section('online',rows,ids+[tid,mid]+tids,[te,me]+ev)
                    batch.finish(p,page);p.close()
                elif bank=='RHB':
                    p,page=open_page('campaign',link(bank));table=p.locator('table').filter(has_text='Currency of Account').first;rows,ids=batch.table(p,page,'campaign',table,group_size=1)
                    # Two official URLs resolve to the same PDF; select the canonical host path.
                    tids,ev=terms('campaign-terms','sg/dam/jcr:');section('campaign',rows,ids+tids,ev)
                    batch.finish(p,page);p.close()
                elif bank=='SBI':
                    p,page=open_page('usd',link(bank));table=p.locator('table').filter(has_text='Promotional Interest Rate').first;rows,ids=batch.table(p,page,'usd',table)
                    ev=[]
                    for key,pattern in [('renewal',r'Applicable for fresh and renewal'),('maximum',r'The minimum deposit amount as indicated'),('channel',r'Walk in to any')]:
                        i,e=txt(key,pattern);ids.append(i);ev.append(e)
                    section('usd',rows,ids,ev,currency='USD');batch.finish(p,page);p.close()
                elif bank=='SCB':
                    p,page=open_page('usd',link(bank));table=p.locator('table').filter(has_text='PROMOTIONAL INTEREST RATE').first;rows,ids=batch.table(p,page,'usd',table,group_size=1)
                    tid,te=txt('fresh-funds',r'For a limited time only, enjoy high returns')
                    tids,ev=terms('usd-terms','sg-usdtd-tnc');section('usd',rows,ids+[tid]+tids,[te]+ev,currency='USD');batch.finish(p,page);p.close()
                elif bank=='ICBC':
                    for cur,label in [('CNY','RMB Fixed Deposit'),('USD','USD Fixed Deposit')]:
                        p,page=open_page(cur,link(bank,'SGD'));p.get_by_text(label,exact=True).filter(visible=True).first.click();p.wait_for_timeout(PAGE_SETTLE_MS)
                        if cur=='USD':
                            heading=p.get_by_text(re.compile(r'^1\.USD Fixed Deposit promotional interest rate')).filter(visible=True).last
                        else:heading=p.get_by_text(re.compile(r'RMB Fixed Deposit promotional interest rate',re.I)).filter(visible=True).last
                        tid,te=batch.text(p,page,cur+'-title',heading);table=heading.locator('xpath=following::table[1]');rows,ids=batch.table(p,page,cur+'-promo',table,group_size=1)
                        ev=[te];ids.append(tid)
                        if cur=='CNY':
                            i,e=txt('CNY-minimum',r'^The minimum deposit amount over counter is RMB');ids.append(i);ev.append(e)
                        else:
                            i,e=txt('USD-minimum',r'Deposit over counter with minimum amount USD');ids.append(i);ev.append(e)
                        section(cur.lower(),rows,ids,ev,currency=cur);batch.finish(p,page);p.close()
                elif bank=='HSBC':
                    p,page=open_page('usd',link(bank));tids,ev=terms('usd-terms','hsbc-usd-time')
                    for aud in ['personal']:
                        names={'elite':r'^For Premier Elite customers:','wealth':r'^For Premier customers with wealth holdings','premier':r'^For Premier customers without wealth holdings:','personal':r'^For Personal Banking customers:'}
                        heading=p.get_by_text(re.compile(names[aud])).filter(visible=True).last
                        # The heading is now a caption INSIDE its table.
                        table=heading.locator('xpath=ancestor::table[1]')
                        if not table.count():table=heading.locator('xpath=following::table').filter(visible=True).first
                        rows,ids=batch.table(p,page,'usd-'+aud,table,group_size=1)
                        h,he=txt('audience-'+aud,names[aud]);section('usd-'+aud,rows,ids+[h]+tids,[he]+ev,currency='USD')
                    # App promotion displayed separately; retain its own terms and channels.
                    tids,ev=terms('aud-gbp-terms','hsbc-aud-gbp-time')
                    for cur in ['AUD','GBP']:
                        tid,te=txt(cur+'-rate',r'^\d\.\d+% p\.a\. on '+cur+r' Time Deposits$')
                        section(cur.lower(),[[te['quote']]],[tid]+tids,[te]+ev,currency=cur)
                    batch.finish(p,page);p.close()
                elif bank=='DBS':
                    p,page=open_page('bonus','https://www.dbs.com.sg/personal/promotion/usdfd-a')
                    table=p.locator('table').filter(has_text='Bonus interest on top of board rate').first;rows,ids=batch.table(p,page,'bonus',table,group_size=1);ev=[]
                    p.get_by_text('How do I enjoy the bonus interest?',exact=True).click();p.wait_for_timeout(PAGE_SETTLE_MS)
                    for key,pattern in [('validity',r'^Offer ends \d{1,2} [A-Za-z]+'),('rate-composition',r'^\* Rate is as of'),('channel',r'^To enjoy the bonus interest on this USD')]:
                        i,e=txt(key,pattern);ids.append(i);ev.append(e)
                    tids,extra=terms('bonus-terms','retail-terms-and-conditions-usd');section('bonus',rows,ids+tids,ev+extra,currency='USD');batch.finish(p,page);p.close()
                elif bank=='BOC':
                    p,page=open_page('index','https://www.bankofchina.com/sg/cn/bocinfo/bi3/bi31/')
                    from urllib.parse import urljoin
                    from market_rates.boc_discovery import latest_promotion_url
                    refs=p.locator('a[href]').evaluate_all('els=>els.map(e=>({text:e.innerText,url:e.href}))')
                    url=latest_promotion_url(refs,datetime.now().strftime('%Y%m%d'));batch.finish(p,page);p.close();p,page=open_page('mobile',url)
                    tables=p.locator('table').filter(has_text='手机银行(*新存单)');table=next(t for t in tables.all() if len(t.locator('table').all())==0)
                    grid=table.evaluate(PHYSICAL);ids=[]
                    first_fx=next((i for i,row in enumerate(grid) if row and row[0].strip() in ['美元','澳元','新西兰元','欧元','英镑','人民币']),None)
                    if first_fx is None:raise ValueError('BOC foreign currency table not found')
                    # Each merged source cell is verified once; no inferred repeat
                    # of merged currency/tenor labels is supplied to the VLM.
                    for i,tr in enumerate(table.locator('tr').all()):
                        for j,cell in enumerate(tr.locator(':scope > td, :scope > th').all()):
                            text=cell.inner_text().strip()
                            if not text:continue
                            # The ordinary table has SGD then foreign currencies.
                            if 2<i<first_fx:continue
                            tid,_=batch.text(p,page,'cell-'+str(i)+'-'+str(j),cell);ids.append(tid)
                    ev=[]
                    for key,pattern in [('validity',r'^本次个人定期存款促销利率有效期'),('new-placement',r'^\*新存单是指'),('personal',r'^以上定期存款促销利率适用于个人客户')]:
                        i,e=txt(key,pattern);ids.append(i);ev.append(e)
                    section('mobile',grid,ids,ev);batch.finish(p,page);p.close()
                elif bank=='CITI':
                    p,page=open_page('conversion',link(bank));table=p.locator('table').filter(has_text='1 Month Promotional').first
                    grid=table.evaluate(PHYSICAL);indexes=[i for i,row in enumerate(grid) if row[0]!='JPY'];rows,ids=batch.table(p,page,'conversion',table,indexes,group_size=1)
                    tids,ev=terms('conversion-terms','fcy-fxtd');section('conversion',rows,ids+tids,ev);batch.finish(p,page);p.close()
                    p,page=open_page('new-funds',link(bank,'SGD'));table=p.locator('table').filter(has_text='Currency / New Funds Time Deposit Amount').first
                    rows,ids=batch.table(p,page,'new-funds',table,[0,2],group_size=1)
                    # Conditions surrounding the table are separate literal tasks.
                    parent=table.locator('xpath=..');(batch.ev/'citi-new-funds-context.txt').write_text(parent.inner_text(),encoding='utf8')
                    ev=[]
                    for key,pattern in [('new-funds-validity',r'Enjoy attractive preferential rates on SGD and USD'),('new-funds-eligibility',r'These promotional rates are open to all existing Citibank customers')]:
                        i,e=txt(key,pattern);ids.append(i);ev.append(e)
                    section('new-funds',rows,ids,ev,currency='USD');batch.finish(p,page);p.close()
                else:raise ValueError('Adapter not implemented '+bank)
                r=batch.save();r['source_file_hashes']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in batch.ev.glob('*.pdf')};save(batch.out/'run.json',r);print(bank,'COMPLETE',flush=True)
            except Exception as e:save(batch.out/'capture-error.json',dict(bank=bank,error=str(e)));failures.append(bank);print(bank,'FAILED',str(e)[:250],flush=True)
            finally:b.close()
    if failures:raise ValueError('Incomplete: '+','.join(failures))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',required=True);a.add_argument('--banks',default='BEA,CIMB,RHB,SBI,SCB,ICBC,HSBC');x=a.parse_args();capture(x.out,x.banks.split(','))

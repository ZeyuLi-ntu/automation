"""Small original-pixel evidence tiles shared by local board adapters."""
import hashlib,re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .common import save, digest
from .browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS


class BoardCapture:
    def __init__(self,out):
        self.out=Path(out);self.ev=self.out/'evidence';self.ev.mkdir(parents=True,exist_ok=False)
        self.prefix=self.out.name+'-';self.pages=[];self.sections=[];self.tasks=[]

    def open(self,context,bank,key,url):
        p=context.new_page();p.set_default_timeout(CONTENT_TIMEOUT_MS)
        resp=p.goto(url,wait_until='domcontentloaded',timeout=PAGE_LOAD_TIMEOUT_MS)
        if not resp or resp.status>=400:raise ValueError('Source unavailable: '+url)
        p.wait_for_timeout(PAGE_SETTLE_MS)
        page=dict(id=self.prefix+key,bank=bank,currency='multi',rate_type='board',url=p.url,ok=True,complete=True,
            captured_at=datetime.now(timezone.utc).isoformat(),images=[],image_hashes={})
        return p,page

    def task(self,page,key,value,image,kind):
        sha=hashlib.sha256((self.ev/image).read_bytes()).hexdigest();tid=self.prefix+key
        self.tasks.append(dict(id=tid,bank=page['bank'],kind=kind,expected=value,images=[image],page_id=page['id'],image_hashes={image:sha}))
        page['images'].append(image);page['image_hashes'][image]=sha
        return tid

    def text(self,p,page,key,loc):
        from scripts.capture_board_wave import shot
        loc=loc.filter(visible=True).first;txt=loc.inner_text().strip();name=self.prefix+key+'.png'
        shot(p,loc,self.ev/name)
        return self.task(page,key,txt,name,'text'),dict(page_id=page['id'],quote=txt,locator=self.prefix+key)

    def table(self,p,page,key,table,row_indices=None,group_size=2,transposed=False):
        from scripts.capture_board_wave import PHYSICAL
        table.wait_for(state='visible',timeout=CONTENT_TIMEOUT_MS)
        original=table.evaluate(PHYSICAL);rows=original
        trs=[tr for tr in table.locator('tr').all() if tr.evaluate('r=>[...r.cells].some(c=>c.innerText.trim())')]
        if len(trs)!=len(rows):raise ValueError('Physical row count changed')
        if transposed:
            cells=trs[0].locator(':scope > th, :scope > td').all()
            a,b=cells[0].bounding_box(),cells[1].bounding_box()
            if abs(a['x']-b['x'])>3 or b['y']<=a['y']:raise ValueError('Expected visually transposed source table')
        indices=list(range(len(rows))) if row_indices is None else list(row_indices)
        rows=[original[i] for i in indices]
        groups=[]
        for index in indices:
            if groups and index==groups[-1][-1]+1 and len(groups[-1])<group_size:groups[-1].append(index)
            else:groups.append([index])
        table.evaluate("e=>{window.__tileFloat=[...document.querySelectorAll('*')].filter(x=>x!==e&&!x.contains(e)&&!e.contains(x)&&['fixed','sticky'].includes(getComputedStyle(x).position)).map(x=>[x,x.style.visibility]);window.__tileFloat.forEach(([x])=>x.style.visibility='hidden')}")
        ids=[]
        try:
            for selected in groups:
                i=selected[0];group=[trs[j] for j in selected];group[0].scroll_into_view_if_needed();p.evaluate('(dy)=>window.scrollBy(0,dy)',group[0].bounding_box()['y']-180);p.wait_for_timeout(SCROLL_SETTLE_MS)
                # A row rectangle includes cells spanning from an earlier row.
                # For a single physical row capture only its own nonempty cells.
                boxes=[tr.bounding_box() for tr in group]
                if len(group)==1:
                    own=[c.bounding_box() for c in group[0].locator(':scope > th, :scope > td').all() if c.inner_text().strip()]
                    if own:boxes=own
                x=min(b['x'] for b in boxes);y=min(b['y'] for b in boxes)
                right=max(b['x']+b['width'] for b in boxes);bottom=max(b['y']+b['height'] for b in boxes)
                if y<0 or bottom>p.viewport_size['height']:raise ValueError('Screenshot would clip a source row')
                name=self.prefix+key+'-'+str(i)+'.png'
                p.screenshot(path=str(self.ev/name),clip=dict(x=x,y=y,width=right-x,height=bottom-y),animations='disabled',timeout=SCREENSHOT_TIMEOUT_MS)
                values=[original[j] for j in selected]
                if transposed:values=[list(row) for row in zip(*values)]
                ids.append(self.task(page,key+'-'+str(i),values,name,'grid'))
                # Record source geometry, never infer cell widths from rates.
                # Only a contiguous, horizontal physical row can be split safely.
                if len(group)==1 and not transposed and len(boxes)==len(values[0]):
                    from market_rates.evidence_repair import source_cell_cuts
                    import struct
                    width=struct.unpack('>I',(self.ev/name).read_bytes()[16:20])[0]
                    cuts=source_cell_cuts(boxes,width)
                    if cuts is not None:
                        self.tasks[-1]['source_cell_cuts']=cuts
                        self.tasks[-1]['source_geometry_image_hash']=self.tasks[-1]['image_hashes'][name]
                lengths=[len(row) for row in values]
                self.tasks[-1]['merged_caption_rows']=[n for n,row in enumerate(values) if len(row)==1 and re.search(r'[A-Za-z]',row[0])]
                if len(values)>1 and (len(set(lengths))>1 or max(lengths)==1):self.tasks[-1]['strict_row_layout']=True
        finally:p.evaluate('()=>window.__tileFloat.forEach(([x,v])=>x.style.visibility=v)')
        if table.evaluate(PHYSICAL)!=original:raise ValueError('Table changed during capture')
        return rows,ids

    def finish(self,p,page):
        page['text']=p.locator('body').inner_text();page['sha256']=hashlib.sha256(page['text'].encode()).hexdigest()
        (self.ev/(page['id']+'.html')).write_text(p.content(),encoding='utf8')
        (self.ev/(page['id']+'.txt')).write_text(page['text'],encoding='utf8');self.pages.append(page)

    def save(self):
        from .pipeline import evidence_index
        today=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        run=dict(id=self.out.name,as_of=today,bank_dates={p['bank']:today for p in self.pages},pages=self.pages,sections=self.sections,tasks=self.tasks,errors=[],evidence_hash=digest(self.pages),task_hash=digest(self.tasks),demo=False)
        save(self.out/'run.json',run);evidence_index(self.pages,self.ev)
        print('Captured',len(self.sections),'sections;',len(self.tasks),'local verification tasks',flush=True)
        return run

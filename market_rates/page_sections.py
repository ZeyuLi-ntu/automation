"""Capture an original webpage section between explicit visible headings."""


def capture_between(page,spec,image_path):
    data=page.evaluate(r'''spec=>{
      const clean=s=>(s||'').replace(/\s+/g,' ').trim();
      const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
      function one(pattern){
        const re=new RegExp(pattern,'i');
        const matches=[...document.body.querySelectorAll('*')].filter(e=>visible(e)&&re.test(clean(e.innerText)));
        const leaves=matches.filter(e=>!matches.some(other=>other!==e&&e.contains(other)));
        if(leaves.length!==1)throw Error('Section heading missing or ambiguous: '+pattern);
        return leaves[0];
      }
      const start=one(spec.start),end=one(spec.end),context=one(spec.context);
      if(!(start.compareDocumentPosition(end)&Node.DOCUMENT_POSITION_FOLLOWING))throw Error('Reversed section boundaries');
      const range=document.createRange();range.setStartBefore(start);range.setEndBefore(end);
      const tables=[...document.querySelectorAll('table')].filter(t=>visible(t)&&range.intersectsNode(t)&&spec.table_headers.every(h=>clean(t.innerText).includes(h)));
      if(tables.length!==1||tables[0].rows.length<2)throw Error('Expected one complete selected promotion table');
      for(const heading of spec.table_headers){if(!clean(tables[0].innerText).includes(heading))throw Error('Rate header changed: '+heading)}
      const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node,parts=[];
      while(node=walker.nextNode())if(node.parentElement&&visible(node.parentElement)&&range.intersectsNode(node)&&clean(node.textContent))parts.push(clean(node.textContent));
      const rects=[...(spec.include_context_in_image===false?[]:[context.getBoundingClientRect()]),...range.getClientRects()];
      const left=Math.max(0,Math.min(...rects.map(r=>r.left))+scrollX),top=Math.max(0,Math.min(...rects.map(r=>r.top))+scrollY);
      const right=Math.min(document.documentElement.scrollWidth,Math.max(...rects.map(r=>r.right))+scrollX);
      const bottom=Math.max(...rects.map(r=>r.bottom))+scrollY;
      if(bottom-top>5000||right-left<300||bottom-top<100)throw Error('Unexpected section dimensions');
      return {text:clean(context.innerText)+'\n'+parts.join('\n'),clip:{x:left,y:top,width:right-left,height:bottom-top}};
    }''',spec)
    page.screenshot(path=str(image_path),full_page=True,clip=data['clip'],animations='disabled')
    return data['text']

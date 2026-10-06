from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1100})
    page.goto('https://sg.statebank/sgd-promotions',wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT_MS);page.wait_for_timeout(PAGE_SETTLE_MS)
    region=page.locator('#column-2:has(.inner-page-content table)')
    print(region.evaluate('e=>{let r=[];for(let x=e;x&&r.length<15;x=x.parentElement){let b=x.getBoundingClientRect();r.push({tag:x.tagName,cls:x.className,id:x.id,x:b.x,y:b.y,w:b.width,h:b.height,overflow:getComputedStyle(x).overflow})}return {ancestors:r,sx:scrollX,sy:scrollY,dh:document.documentElement.scrollHeight,bh:document.body.scrollHeight}}'))
    region.screenshot(path='runs/sbi-crop-probe.png', timeout=SCREENSHOT_TIMEOUT_MS)
    clip=region.evaluate('e=>{let b=e.getBoundingClientRect();return {x:b.x+scrollX-24,y:b.y+scrollY-24,width:b.width+48,height:b.height+48}}')
    print('clip',clip)
    page.screenshot(path='runs/sbi-padded-probe.png',clip=clip,full_page=True,animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS)
    browser.close()

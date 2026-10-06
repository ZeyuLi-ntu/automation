"""Read-only production UI checks; never submits an edit or rebuild."""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from market_rates.common import load,save
if __name__=='__main__':
    p=Path(load('outputs/latest-board-pilot.json')['output'])
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:8766');page.locator('article').first.wait_for()
        page.select_option('#currency','CNH');expect(page.locator('article')).to_have_count(4)
        expect(page.locator('article .badge').filter(has_text='规则排除，保留明细')).to_have_count(4)
        page.select_option('#bank','SBI');page.select_option('#currency','USD');expect(page.locator('article')).to_have_count(7)
        expect(page.locator('article .badge').filter(has_text='已人工处理')).to_have_count(7)
        page.select_option('#bank','BOC');page.select_option('#currency','EUR');expect(page.locator('article')).to_have_count(12)
        page.locator('article summary').first.click();page.screenshot(path=str(p/'review-ui.png'));assert not errors
        save(p/'ui-checks.json',dict(passed=True,checks=['CNH detail-only filter','SBI USD seven approved records','BOC EUR twelve records','No browser errors'],production_ledger_untouched=True))
        b.close();print('Board UI checks passed')

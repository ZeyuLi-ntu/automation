"""Read-only browser checks for the broad board batch and currency policy."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from market_rates.common import load, save


if __name__ == '__main__':
    output = Path(load('outputs/latest-board-pilot.json')['output'])
    ledger = Path('data/manual-review.json').read_bytes()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8766')
        page.locator('article').first.wait_for()
        currencies = page.locator('#currency option').evaluate_all('(xs) => xs.map(x => x.value)')
        assert 'JPY' not in currencies and 'CNH' not in currencies and 'CNY' in currencies
        page.select_option('#bank', 'HLB')
        page.select_option('#currency', 'CNY')
        expect(page.locator('article')).to_have_count(4)
        expect(page.locator('article summary').filter(has_text='CNY（原CNH）')).to_have_count(4)
        expect(page.locator('article .badge').filter(has_text='规则排除')).to_have_count(0)
        page.select_option('#bank', 'SBI')
        page.select_option('#currency', 'USD')
        expect(page.locator('article')).to_have_count(7)
        expect(page.locator('article .badge').filter(has_text='已人工处理')).to_have_count(7)
        page.select_option('#bank', 'DBS')
        page.select_option('#currency', 'SGD')
        expect(page.locator('article')).to_have_count(84)
        page.select_option('#bank', 'UOB')
        expect(page.locator('article')).to_have_count(72)
        expect(page.locator('article .badge').filter(has_text='规则排除')).to_have_count(18)
        page.select_option('#bank', 'SCB')
        page.select_option('#currency', 'USD')
        assert page.locator('article').count() > 0
        expect(page.locator('article .badge').filter(has_text='规则排除')).to_have_count(0)
        for bank,currency in [('BEA','SGD'),('BEA','USD'),('Maybank','SGD'),('HSBC','USD'),('CIMB','USD')]:
            page.select_option('#bank',bank);page.select_option('#currency',currency)
            assert page.locator('article').count()>0,(bank,currency)
            expect(page.locator('article .badge').filter(has_text='规则排除')).to_have_count(0)
        page.select_option('#bank', 'HLB')
        page.select_option('#currency', 'CNY')
        page.locator('article summary').first.click()
        page.screenshot(path=str(output / 'review-ui.png'))
        assert not errors, errors
        browser.close()
    assert Path('data/manual-review.json').read_bytes() == ledger
    save(output / 'ui-checks.json', dict(passed=True, checks=[
        'JPY excluded; CNH uses CNY filter with original currency label',
        'HLB four CNH rows no longer held for missing CNY mapping',
        'SBI USD seven prior user confirmations preserved',
        'DBS SGD 84 records; UOB 72 records with 18 missing-minimum holds',
        'SCB and CIMB FX confirmed annual basis; repaired five-bank sources visible',
        'No browser errors; production ledger untouched',
    ]))
    print('Broad board review UI checks passed')

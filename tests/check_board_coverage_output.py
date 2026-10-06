"""Read-only checks for the dated Bank List audit and its user-visible pages."""
import argparse,asyncio,hashlib
from pathlib import Path
from playwright.async_api import async_playwright
from market_rates.common import load,save
from scripts.probe_board_all import wait_for_dynamic_board


async def check(out):
    out=Path(out);r=load(out/'board-coverage.json');checks=[]
    def ck(name,value):
        checks.append(dict(name=name,passed=bool(value)))
    # Independent transcription of the user's required board matrix. Blank
    # EUR cells for HSBC/UOB must not become invented requirements.
    scope={
        'BEA':'SGD USD CNY AUD NZD CAD HKD EUR GBP','BOC':'SGD USD CNY AUD NZD CAD HKD EUR GBP',
        'CIMB':'SGD USD CNY AUD NZD CAD EUR GBP','CITI':'SGD','DBS':'SGD USD AUD NZD CAD HKD EUR GBP',
        'HLB':'SGD USD CNY AUD NZD HKD GBP','HLF':'SGD','HSBC':'SGD USD AUD NZD CAD HKD GBP',
        'ICBC':'SGD USD CNY','Maybank':'SGD USD AUD NZD CAD EUR GBP','OCBC':'SGD USD AUD NZD CAD HKD EUR GBP',
        'RHB':'SGD USD CNY AUD NZD CAD HKD EUR GBP','SBI':'SGD USD AUD GBP','SCB':'SGD USD AUD NZD CAD HKD EUR GBP',
        'SingFinance':'SGD','Singapura Finance':'SGD','UOB':'SGD USD CNY AUD NZD CAD HKD GBP'}
    expected={(bank,cur) for bank,currencies in scope.items() for cur in currencies.split()}
    ck('exact screenshot scope',expected=={(x['bank'],x['currency']) for x in r['rows']} and len(expected)==99)
    ck('saved current workbook inspected',r['saved_output_inspected'])
    ck('partial output cannot claim complete',not r['required_pair_availability_complete'] and r['missing_or_fully_held']>0)
    for row in r['rows']:
        if row['status']=='missing':
            ck('missing source located '+row['bank']+'/'+row['currency'],bool(row['investigation'].get('evidence')))
        for evidence in row['investigation'].get('evidence',[]):ck('evidence file '+row['cell'],Path(evidence['path']).is_file())
    snapshots=load(out/'coverage-preservation-before.json')
    for path,sha in snapshots.items():ck('preserved '+Path(path).name,hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha)
    async with async_playwright() as pw:
        b=await pw.chromium.launch(headless=True)
        page=await b.new_page(viewport={'width':1680,'height':1200})
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto((out/'board-coverage.html').resolve().as_uri())
        ck('matrix shows 17 banks',await page.locator('.matrix tbody tr').count()==17)
        ck('all required cells link to causes',await page.locator('.matrix td a').count()==99)
        await page.screenshot(path=str(out/'board-coverage-preview.png'))
        await page.goto((out/'table-validation.html').resolve().as_uri())
        ck('numeric QA page exposes gaps',await page.get_by_text('挂牌覆盖：Bank List 应有',exact=False).count()==1)
        await page.goto('http://127.0.0.1:8766/')
        await page.locator('#coverage-summary').wait_for(state='visible',timeout=30000)
        ck('manual UI shows whole scope','99' in await page.locator('#coverage-summary').inner_text())
        ck('human pending is separate',await page.get_by_text('数据可用；待人工验收（非缺失）',exact=True).count()>0)
        ck('no browser errors',not errors)
        await page.screenshot(path=str(out/'board-coverage-review-preview.png'))
        await page.set_content('<p>Loading...</p><table style="display:none"><tr><td>1.5</td></tr></table>')
        try:
            await asyncio.wait_for(wait_for_dynamic_board(page,'OCBC'),0.3)
            ck('hidden/loading table rejected',False)
        except asyncio.TimeoutError:ck('hidden/loading table rejected',True)
        await page.set_content('<p>Loading...</p><script>setTimeout(()=>document.body.innerHTML="<table><tr><td>0.0000</td></tr></table>",200)</script>')
        await asyncio.wait_for(wait_for_dynamic_board(page,'DBS'),5)
        ck('waits for visible data including zero','0.0000' in await page.locator('body').inner_text())
        await b.close()
    result=dict(passed=all(c['passed'] for c in checks),count=len(checks),failed=[c for c in checks if not c['passed']])
    save(out/'coverage-checks.json',result);print(result)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',required=True)
    asyncio.run(check(a.parse_args().output))

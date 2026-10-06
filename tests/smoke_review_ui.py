"""Real-browser form regression using only synthetic rows in a temporary project."""
from copy import deepcopy
from pathlib import Path
from http.server import ThreadingHTTPServer
import tempfile,threading,json,urllib.request,urllib.error
from playwright.sync_api import sync_playwright
from market_rates.demo import offer
from market_rates.common import save,digest,load
from market_rates.manual_review import ledger,effective_offers
from scripts.review_server import ReviewApp,ReviewHTTPServer,handler,running_server

def main():
    with tempfile.TemporaryDirectory(prefix='rate-review-ui-') as tmp:
        root=Path(tmp);out=root/'outputs/test';runpath=root/'runs/test'
        row=offer('BEA','bea-sgd-promo',rate='1.7')
        run=dict(id='synthetic-only',as_of='2026-09-27',bank_dates={'BEA':'2026-09-27'},pages=[],evidence_hash=digest([]),
          llm=dict(offers=[row]),vlm=dict(offers=[deepcopy(row)]))
        save(runpath/'run.json',run)
        save(out/'table-validation-plan.json',dict(source_run=str(runpath),as_of=run['as_of'],bank_dates=run['bank_dates'],banks=['BEA'],
          report_output=str(out/'report.xlsx'),rainbow_output=str(out/'rainbow.xlsx')))
        app=ReviewApp(root,out);server=ReviewHTTPServer(('127.0.0.1',0),handler(app))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
        try:
            assert running_server(url)
            try:
                duplicate=ReviewHTTPServer(('127.0.0.1',server.server_port),handler(app))
            except OSError:pass
            else:
                duplicate.server_close();raise AssertionError('duplicate local listener must be rejected')
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1400,'height':1050});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)));page.goto(url)
                page.locator('article summary').first.click();form=page.locator('article').first
                form.locator('[data-field=rate_pct]').fill('1.9');form.get_by_label('复核人',exact=True).fill('Synthetic UI test')
                form.get_by_label('修正原因',exact=True).fill('Synthetic test only')
                form.get_by_role('button',name='保存本条').click()
                page.get_by_text('已保存。重新生成后同步到两份表格。',exact=True).wait_for()
                assert ledger(root)['version']==1
                assert effective_offers(run,root)[0][0]['rate_pct']=='1.9'
                assert load(runpath/'run.json')==run
                page.get_by_role('button',name='刷新',exact=True).click()
                page.locator('article summary').filter(has_text='1.9%').wait_for()
                page.locator('article summary').first.click();form=page.locator('article').first
                form.locator('.actions select').select_option('reset')
                form.get_by_label('修正原因',exact=True).fill('Undo synthetic revision')
                form.get_by_role('button',name='保存本条').click()
                page.get_by_text('已保存。重新生成后同步到两份表格。',exact=True).wait_for()
                assert effective_offers(run,root)[0][0]['rate_pct']=='1.7'
                assert ledger(root)['version']==2
                # Tokenless writes and cross-origin writes never touch the ledger.
                response=page.request.post(url+'/api/save',data={})
                assert response.status==403
                response=page.request.post(url+'/api/save',data={},headers={'X-Review-Token':app.token,'Origin':'https://unrelated.example'})
                assert response.status==403
                response=page.request.get(url+'/file/..%2F..%2Fsecret.txt')
                assert response.status in [400,404]
                assert not errors,errors
                browser.close()
            print(json.dumps(dict(passed=True,save=True,refresh=True,reset=True,raw_unchanged=True,
              write_token=True,origin=True,path_boundary=True,production_ledger_untouched=True)))
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()

"""Read-only local browser check against a previously verified BOC board batch."""
import argparse
import re
from pathlib import Path
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright
from market_rates.common import load,save
from market_rates.boc_discovery import latest_board_announcement
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS,PAGE_SETTLE_MS
from scripts.capture_board_batch import GRID


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    source=load(Path(a.run)/'run.json');out=Path(a.out);out.mkdir(exist_ok=False)
    pages=[p for p in source['pages'] if p['bank']=='BOC' and p.get('grid') and p['id'].endswith('-rates')]
    if not pages:raise ValueError('No verified BOC table to compare')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,channel='chrome')
        try:
            page=browser.new_page(viewport={'width':1440,'height':1600})
            page.goto('https://www.bankofchina.com/sg/cn/bocinfo/bi3/',timeout=PAGE_LOAD_TIMEOUT_MS,wait_until='domcontentloaded')
            page.wait_for_timeout(PAGE_SETTLE_MS)
            links=page.locator('a[href]').evaluate_all('xs=>xs.map(x=>({text:x.innerText.trim(),url:x.href}))')
            selected,candidates=latest_board_announcement(links,datetime.now().strftime('%Y%m%d'))
            (out/'index.html').write_text(page.content(),encoding='utf8')
            page.goto(selected['url'],timeout=PAGE_LOAD_TIMEOUT_MS,wait_until='domcontentloaded');page.wait_for_timeout(PAGE_SETTLE_MS)
            table=page.locator('.trs_editor_view > table').filter(has_text='年利率').first
            grid=table.evaluate(GRID);(out/'source.html').write_text(page.content(),encoding='utf8')
            table.screenshot(path=str(out/'source-table.png'))
            same_url=all(p['url']==selected['url'] for p in pages)
            by_currency={}
            for row in grid[2:]:
                m=re.search(r'\(([A-Z]{3})\)',row[0])
                if not m:raise ValueError('Unrecognized BOC currency row')
                cur='CNY' if m[1]=='RMB' else m[1]
                by_currency.setdefault(cur,[]).append(row)
            same_rows=all(p['grid'][:2]==grid[:2] and p['grid'][2:]==by_currency.get(p['currency']) for p in pages)
            result=dict(checked_at=datetime.now(timezone.utc).isoformat(),selected=selected,candidates=candidates,
                        source_run=str(Path(a.run).resolve()),same_url=same_url,same_rows=same_rows,currencies=[p['currency'] for p in pages])
            save(out/'check.json',result)
            if not (same_url and same_rows):raise ValueError('BOC source changed; recapture and verify before rebuilding')
            print(result)
        finally:browser.close()


if __name__=='__main__':main()

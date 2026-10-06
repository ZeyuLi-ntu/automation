"""Read a bank URL from the supplied workbook and inspect capture regions."""
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS
import argparse
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright
from market_rates.xlsx_read import read_xlsx
from market_rates.common import save

parser = argparse.ArgumentParser()
parser.add_argument("--links", required=True)
parser.add_argument("--cell", default="D67")
parser.add_argument("--out", required=True)
args = parser.parse_args()
book = read_xlsx(args.links)
name, cells = next(iter(book.items()))
url = cells[args.cell]
out = Path(args.out)
out.mkdir(parents=True, exist_ok=False)
save(out / "source.json", {"workbook": str(Path(args.links).resolve()), "sheet": name, "cell": args.cell,
                          "url": url, "workbook_sha256": hashlib.sha256(Path(args.links).read_bytes()).hexdigest()})
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, locale="en-SG")
        response = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        page.locator("body").wait_for(timeout=CONTENT_TIMEOUT_MS)
        page.wait_for_timeout(PAGE_SETTLE_MS)
        body = page.locator("body").inner_text()
        (out / "body.txt").write_text(body, encoding="utf8")
        (out / "page.html").write_text(page.content(), encoding="utf8")
        tables = page.locator("table").evaluate_all("els => els.map((e,i)=>({index:i,text:e.innerText,parents:Array.from((function*(x){for(let n=0;x&&n<6;n++,x=x.parentElement)yield x})(e)).map(x=>({tag:x.tagName,id:x.id,class:x.className,text:x.innerText.slice(0,180)}))}))")
        links = page.locator("a[href]").evaluate_all(r"els => els.map(e=>({text:e.innerText,url:e.href})).filter(e=>/terms|fresh.funds|\.pdf/i.test(e.text+' '+e.url))")
        save(out / "inspection.json", {"requested_url": url, "final_url": page.url,
                                       "http_status": response.status if response else None,
                                       "captured_at": datetime.now(timezone.utc).isoformat(),
                                       "tables": tables, "links": links,
                                       "text_chars": len(body)})
        print(json.dumps({"final_url": page.url, "http_status": response.status if response else None,
                          "tables": tables, "links": links, "text_chars": len(body)}, ensure_ascii=False))
    finally:
        browser.close()

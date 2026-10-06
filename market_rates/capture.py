"""Bounded official-site discovery; archive text and tiled visual evidence."""
from __future__ import annotations
from market_rates.browser_wait import PAGE_LOAD_TIMEOUT_MS, CONTENT_TIMEOUT_MS, SCREENSHOT_TIMEOUT_MS, PAGE_SETTLE_MS, SCROLL_SETTLE_MS

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag
from .common import save
from .workbook_policy import bank_in_scope


def allowed(url, domains):
    parsed = urlparse(url)
    return parsed.scheme in ("https", "http") and parsed.hostname in domains and not parsed.username and not parsed.password


def capture_sources(config, out):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError('安装采集依赖: pip install -e ".[live]"，再运行 python -m playwright install chromium') from exc
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    pages, errors = [], []
    sources = [s for s in config["sources"] if s.get("enabled") and bank_in_scope(s['bank'])]
    if not sources:
        raise ValueError("没有启用的官方来源，请先检查config/sources.json")
    with sync_playwright() as pw:
        if config.get('browser_channel')=='chrome':
            browser = pw.chromium.launch(channel='chrome',headless=False,args=['--start-minimized'])
        else:
            browser = pw.chromium.launch(headless=True,args=['--disable-http2'])
        try:
            for source in sources:
                domains = source["domains"]
                queue = [(url, 0) for url in source["urls"]]
                seen = set()
                count = 0
                scale=source.get('device_scale_factor',1)
                if scale not in [1,2,3]:raise ValueError('Unsupported capture pixel ratio')
                context = browser.new_context(viewport={"width": 1440, "height": 1100}, locale="en-SG",device_scale_factor=scale)
                # Navigation may not silently follow an off-domain replacement page.
                def route_handler(route):
                    if route.request.is_navigation_request() and not allowed(route.request.url, domains):
                        route.abort()
                    else:
                        route.continue_()
                context.route("**/*", route_handler)
                try:
                    while queue and count < source.get("max_pages", 8):
                        url, depth = queue.pop(0)
                        url = urldefrag(url)[0]
                        if url in seen or not allowed(url, domains):
                            continue
                        seen.add(url); count += 1
                        page_id = hashlib.sha256((source["id"] + url).encode()).hexdigest()[:20]
                        page = context.new_page()
                        try:
                            # PDF attachment uses browser request, preserving the same session.
                            if urlparse(url).path.lower().endswith(".pdf"):
                                import pymupdf
                                response = context.request.get(url, timeout=PAGE_LOAD_TIMEOUT_MS, max_redirects=0)
                                pdf_url=url
                                for _ in range(3):
                                    if response.status not in (301,302,303,307,308):break
                                    target=urljoin(pdf_url,response.headers.get('location',''))
                                    if not allowed(target,domains) or target==pdf_url:raise ValueError('PDF redirect left registered domain or looped')
                                    pdf_url=target;response=context.request.get(pdf_url,timeout=PAGE_LOAD_TIMEOUT_MS,max_redirects=0)
                                if response.status != 200:
                                    raise ValueError(f"PDF HTTP {response.status}")
                                data = response.body()
                                if not data.startswith(b"%PDF"):
                                    raise ValueError("附件不是PDF")
                                (out / f"{page_id}.pdf").write_bytes(data)
                                doc = pymupdf.open(stream=data, filetype="pdf")
                                if len(doc) > config.get("max_pdf_pages", 30):
                                    raise ValueError("PDF页数超限，需要指定范围；未截断采集")
                                images = []
                                texts = []
                                for index, pdfpage in enumerate(doc):
                                    name = f"{page_id}_p{index+1}.png"
                                    pdfpage.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(out / name)
                                    images.append(name)
                                    texts.append(f"[PDF page {index+1}]\n" + pdfpage.get_text())
                                body, final, complete = "\n".join(texts), pdf_url, True
                            else:
                                for attempt in range(3):
                                    try:
                                        response = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
                                        break
                                    except Exception:
                                        if attempt==2:raise
                                        page.wait_for_timeout(PAGE_SETTLE_MS)
                                if not response or response.status >= 400:
                                    raise ValueError(f"页面HTTP {response.status if response else '无响应'}")
                                if not allowed(page.url, domains):
                                    raise ValueError("跳转出已登记官方域名")
                                # Some sites reveal the body after their initial scripts
                                # settle. This explicit bounded delay is source-scoped.
                                settle = source.get('settle_ms', 0)
                                if type(settle) is not int or not 0 <= settle <= 30000:
                                    raise ValueError('settle_ms must be between 0 and 30000')
                                page.wait_for_timeout(max(PAGE_SETTLE_MS, settle))
                                # A zero-height body may contain visible positioned
                                # children (HLF). Test the selected content itself below.
                                page.locator("body").wait_for(state='attached', timeout=CONTENT_TIMEOUT_MS)
                                for selector in source.get("expand_selectors", []):
                                    for button in page.locator(selector).all():
                                        button.click(timeout=CONTENT_TIMEOUT_MS)
                                # Load lazy content using bounded scroll; do not bypass logins/CAPTCHAs.
                                last_height = 0
                                for _ in range(6):
                                    height = page.evaluate("document.documentElement.scrollHeight")
                                    if height == last_height:
                                        break
                                    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                                    page.wait_for_timeout(SCROLL_SETTLE_MS)
                                    last_height = height
                                page.evaluate("window.scrollTo(0,0)")
                                def dismiss_overlays():
                                    for selector in source.get('dismiss_selectors',[]):
                                        close=page.locator(selector)
                                        if close.count() and close.first.is_visible():
                                            close.first.click(timeout=CONTENT_TIMEOUT_MS)
                                            page.wait_for_timeout(SCROLL_SETTLE_MS)
                                dismiss_overlays()
                                full_body = page.locator("body").inner_text()
                                final = page.url
                                if re.search(r"verify you are human|access denied|captcha", full_body, re.I):
                                    raise ValueError("访问验证或拦截页，需人工处理")
                                (out / f"{page_id}.html").write_text(page.content(), encoding="utf8")
                                (out / f"{page_id}.full.txt").write_text(full_body, encoding="utf8")
                                images = []
                                selectors = source.get("capture_selectors", []) or [u['selector'] for u in source.get('capture_units', [])]
                                if selectors:
                                    regions = [page.locator(selector) for selector in selectors]
                                    if any(region.count() != 1 or not region.is_visible() for region in regions):
                                        raise ValueError("已配置的产品区域未唯一匹配或不可见，不能任意抓取其他区域")
                                    region_texts=[]
                                    for index, region in enumerate(regions):
                                        name = f"{page_id}_region{index+1}.png"
                                        unit=(source.get('capture_units') or [{} for _ in regions])[index]
                                        if unit.get('section_between'):
                                            from .page_sections import capture_between
                                            region_texts.append(capture_between(page,unit['section_between'],out/name))
                                        elif unit.get('end_before'):
                                            # Preserve a literal contiguous table prefix, including merged headers.
                                            # The next currency row is the visible scope boundary; no text is redrawn.
                                            boundary=region.locator(unit['end_before'])
                                            if boundary.count()!=1:raise ValueError('Table scope boundary missing or ambiguous')
                                            page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(SCROLL_SETTLE_MS)
                                            rect=region.bounding_box();end=boundary.bounding_box()
                                            if not rect or not end or end['y']<=rect['y']:raise ValueError('Invalid visible table scope')
                                            page.screenshot(path=str(out/name),full_page=True,clip=dict(x=rect['x'],y=rect['y'],width=rect['width'],height=end['y']-rect['y']),animations='disabled', timeout=SCREENSHOT_TIMEOUT_MS)
                                            region_texts.append(region.evaluate('''(table,label)=>{
                                              let grid=[],y=0;for(const row of table.querySelectorAll('tr')){
                                                if([...row.cells].some(c=>c.innerText.trim()===label))break;
                                                grid[y]??=[];let x=0;
                                                for(const cell of row.cells){while(grid[y][x]!==undefined)x++;
                                                  for(let dy=0;dy<cell.rowSpan;dy++){grid[y+dy]??=[];for(let dx=0;dx<cell.colSpan;dx++)grid[y+dy][x+dx]=cell.innerText.trim()}
                                                  x+=cell.colSpan;
                                                }y++;
                                              }return grid.slice(0,y).map(r=>r.join(' | ')).join('\\n')
                                            }''',unit.get('end_before_text') or boundary.locator('td,th').first.inner_text().strip()))
                                        else:
                                            if source.get('dismiss_selectors'):
                                                region.scroll_into_view_if_needed(timeout=CONTENT_TIMEOUT_MS)
                                                page.wait_for_timeout(PAGE_SETTLE_MS)
                                                dismiss_overlays()
                                            region.screenshot(path=str(out / name), animations="disabled", timeout=SCREENSHOT_TIMEOUT_MS)
                                            if unit.get('table_grid'):
                                                region_texts.append(region.evaluate('''table=>{let grid=[],y=0;for(const row of table.querySelectorAll('tr')){grid[y]??=[];let x=0;for(const cell of row.cells){while(grid[y][x]!==undefined)x++;for(let dy=0;dy<cell.rowSpan;dy++){grid[y+dy]??=[];for(let dx=0;dx<cell.colSpan;dx++)grid[y+dy][x+dx]=cell.innerText.trim()}x+=cell.colSpan}y++}return grid.slice(0,y).map(r=>r.join(' | ')).join('\\n')}'''))
                                            else:region_texts.append(region.inner_text())
                                        images.append(name)
                                    body="\n\n".join(region_texts)
                                    complete=bool(body.strip())
                                else:
                                    body = full_body
                                    height = page.evaluate("document.documentElement.scrollHeight")
                                    positions = list(range(0, height, 900))
                                    if len(positions) > config.get("max_tiles", 30):
                                        raise ValueError("页面过长，需要分区采集；未静默截断")
                                    for index, y in enumerate(positions):
                                        page.evaluate("y => window.scrollTo(0,y)", y)
                                        name = f"{page_id}_tile{index+1}.png"
                                        page.screenshot(path=str(out / name), animations="disabled", timeout=SCREENSHOT_TIMEOUT_MS)
                                        images.append(name)
                                    complete = compact(body) == compact(page.locator("body").inner_text())
                                links = page.locator("a[href]").evaluate_all("els => els.map(e => ({url:e.href,text:e.innerText}))")
                                if depth < source.get("max_depth", 1):
                                    for link in links:
                                        if re.search(source.get("link_pattern", r"deposit|fixed|time.deposit|promotion|rates|\.pdf"),
                                                     link["text"] + " " + link["url"], re.I):
                                            candidate = urljoin(final, link["url"])
                                            if allowed(candidate, domains) and urldefrag(candidate)[0] not in seen:
                                                queue.append((candidate, depth + 1))
                            (out / f"{page_id}.txt").write_text(body, encoding="utf8")
                            record = {"id": page_id, "bank": source["bank"], "url": final, "requested_url": url,
                                          "captured_at": datetime.now(timezone.utc).isoformat(), "text": body,
                                          "images": images, "ok": True, "complete": complete,
                                          "capture_scope": "pdf" if urlparse(url).path.lower().endswith(".pdf") else ("configured_regions" if source.get("capture_selectors") else "full_page"),
                                          "capture_selectors": source.get("capture_selectors", []) if not urlparse(url).path.lower().endswith(".pdf") else [],
                                          "sha256": hashlib.sha256(body.encode()).hexdigest(),
                                          "image_hashes": {i: hashlib.sha256((out / i).read_bytes()).hexdigest() for i in images}}
                            if source.get('capture_units') and record['capture_scope'] != 'pdf':
                                record['capture_scope'] = 'configured_units'
                                record['units'] = [{**u, 'image': images[n], 'text': region_texts[n]}
                                                   for n, u in enumerate(source['capture_units'])]
                            record['product_ids'] = source.get('product_ids', [])
                            record['terms_role'] = source.get('terms_role', 'primary')
                            pages.append(record)
                        except Exception as exc:
                            if not urlparse(url).path.lower().endswith('.pdf'):
                                try:(out / f'{page_id}.failure.html').write_text(page.content(), encoding='utf8')
                                except Exception:pass # Preserve the original navigation error.
                            errors.append(f'{source["bank"]} {url}: {type(exc).__name__}: {str(exc)[:250]}')
                        finally:
                            page.close()
                    remaining = {urldefrag(u)[0] for u, _ in queue} - seen
                    if remaining:
                        errors.append(f'{source["bank"]}来源发现达到上限，仍有{len(remaining)}个候选链接待核查')
                finally:
                    context.close()
        finally:
            browser.close()
    save(out / "capture.json", {"pages": pages, "errors": errors})
    return pages, errors


def compact(s):
    return " ".join(s.split())

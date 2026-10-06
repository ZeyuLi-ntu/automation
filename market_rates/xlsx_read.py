"""Read existing OOXML without modifying or resaving the workbook."""
from __future__ import annotations

import hashlib
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

def merged_ranges(path):
    """Read native merges for exact preservation across column insertion."""
    result={}
    with zipfile.ZipFile(path) as z:
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).find(M+'sheets'):
            target=rels[sheet.attrib[REL+'id']];name=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            result[sheet.attrib['name']]=[r.attrib['ref'] for r in ET.fromstring(z.read(name)).findall(M+'mergeCells/'+M+'mergeCell')]
    return result


def read_hyperlinks(path):
    """External hyperlink targets, separate from user-visible cell text."""
    result={}
    with zipfile.ZipFile(path) as z:
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).find(M+'sheets'):
            target=rels[sheet.attrib[REL+'id']]
            name=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            rp=posixpath.join(posixpath.dirname(name),'_rels',posixpath.basename(name)+'.rels')
            external={r.attrib['Id']:r.attrib.get('Target') for r in ET.fromstring(z.read(rp)) if r.attrib.get('TargetMode')=='External'} if rp in z.namelist() else {}
            result[sheet.attrib['name']]={h.attrib['ref']:external[h.attrib[REL+'id']] for h in ET.fromstring(z.read(name)).findall(M+'hyperlinks/'+M+'hyperlink') if h.attrib.get(REL+'id') in external}
    return result


def read_xlsx(path, formulas=False, merge_anchors_only=False):
    result = {}
    with zipfile.ZipFile(path) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = ["".join(e.itertext()) for e in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        rels = {r.attrib["Id"]: r.attrib["Target"] for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).find(M + "sheets"):
            target = rels[sheet.attrib[REL + "id"]]
            name = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            root = ET.fromstring(z.read(name))
            cells = {}
            for c in root.findall(".//" + M + "sheetData/" + M + "row/" + M + "c"):
                typ = c.attrib.get("t")
                raw = c.find(M + "v")
                value = raw.text if raw is not None else None
                if typ == "s" and value is not None:
                    value = strings[int(value)]
                elif typ == "inlineStr":
                    inline = c.find(M + "is")
                    value = "".join(inline.itertext()) if inline is not None else None
                formula = c.find(M + "f")
                cells[c.attrib["r"]] = "=" + (formula.text or "") if formulas and formula is not None else value
            if merge_anchors_only:
                def position(address):
                    label,row=re.fullmatch(r'([A-Z]+)(\d+)',address).groups();col=0
                    for char in label:col=26*col+ord(char)-64
                    return col,int(row)
                def column(col):
                    label=''
                    while col:col,n=divmod(col-1,26);label=chr(65+n)+label
                    return label
                for merge in root.findall(M+'mergeCells/'+M+'mergeCell'):
                    start,_,end=merge.attrib['ref'].partition(':');c1,r1=position(start);c2,r2=position(end or start)
                    for col in range(c1,c2+1):
                        label=column(col)
                        for row in range(r1,r2+1):
                            if (col,row)!=(c1,r1):cells.pop(label+str(row),None)
            result[sheet.attrib["name"]] = cells
    return result


def import_links(path):
    sheets = read_xlsx(path)
    cells = next(iter(sheets.values()))
    maxrow = max(int(re.search(r"\d+", c)[0]) for c in cells)
    sources = []
    bank, currency = None, None
    seen = set()
    for r in range(2, maxrow + 1):
        if cells.get(f"A{r}"):
            bank, currency = cells[f"A{r}"].strip(), None
        currency = cells.get(f"B{r}") or currency
        category = cells.get(f"C{r}") or "unknown"
        url = cells.get(f"D{r}") or ""
        if not bank or not url.startswith(("http://", "https://")) or (bank, url) in seen:
            continue
        seen.add((bank, url))
        sources.append({"id": hashlib.sha256((bank + url).encode()).hexdigest()[:12], "bank": bank,
                        "enabled": False, "currency_hint": currency, "category_hint": category,
                        "domains": [urlparse(url).hostname], "urls": [url], "max_pages": 8, "max_depth": 1,
                        "expand_selectors": []})
    return sources


def template_candidates(path):
    """Candidates are never assumed to be confirmed product-to-cell mappings."""
    book = read_xlsx(path)
    cells = book["SGD促销"]
    candidates, tenor = [], None
    for r in range(1, max(int(re.search(r"\d+", c)[0]) for c in cells) + 1):
        bank = cells.get(f"A{r}")
        if bank and re.fullmatch(r"\d+ Months?", bank.strip()):
            tenor = bank.split()[0] + "M"
        elif bank and tenor and bank.strip() not in ("日期", "银行"):
            candidates.append({"bank_label": bank.strip(), "display_tenor": tenor, "row": r,
                               "condition": cells.get(f"B{r}"), "product_id": "", "confirmed": False})
    return {"sheet": "SGD促销", "current_column": 3,
            "template_sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(), "candidates": candidates}

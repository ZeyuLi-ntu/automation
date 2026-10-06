import json
from pathlib import Path
from html.parser import HTMLParser

class Links(HTMLParser):
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'a' and any(x in d.get('href','') for x in ('fixed', 'deposit', '.pdf')):
            urls.add(d['href'])

for bank, directory in [('HLF','HLF-retry'),('CIMB','CIMB'),('RHB','RHB')]:
    p = Path('runs/three-bank-discovery')/directory
    j = json.loads((p/'inspection.json').read_text(encoding='utf8'))
    print(bank,[(s['tag'],s['id'],s['title']) for s in j.get('sections',[]) if any(t in s['id'] for t in ['promo','rate','terms','apply','digital'])])
    urls = set(); Links().feed((p/'page.html').read_text(encoding='utf8'))
    print('\n'.join(sorted(urls)))

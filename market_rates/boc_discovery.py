"""BOC announcement titles mix full-width and ASCII punctuation."""
import re
import unicodedata
from .capture import allowed


def latest_promotion_url(links, today):
    candidates=[]
    for link in links:
        title=unicodedata.normalize('NFKC',link['text'])
        match=re.fullmatch(r'\s*个人定期存款促销利率\s*\(\s*(\d{8})\s*\)\s*',title)
        if match and match[1]<=today and allowed(link['url'],['www.bankofchina.com','bankofchina.com']):
            candidates.append((match[1],link['url']))
    if not candidates:raise ValueError('No BOC promotion announcement found')
    date=max(d for d,_ in candidates);urls={u for d,u in candidates if d==date}
    if len(urls)!=1:raise ValueError('Ambiguous latest BOC announcement')
    return urls.pop()


def latest_board_announcement(links,today):
    """Choose the latest published board notice, even if months old or unchanged."""
    candidates=[]
    for link in links:
        title=unicodedata.normalize('NFKC',link['text'])
        match=re.fullmatch(r'\s*个人定期存款挂牌利率\s*\(\s*(\d{8})\s*\)\s*',title)
        if match and match[1]<=today and allowed(link['url'],['www.bankofchina.com','bankofchina.com']):
            candidates.append(dict(link,date=match[1]))
    if not candidates:raise ValueError('No BOC board announcement found')
    date=max(x['date'] for x in candidates);latest=[x for x in candidates if x['date']==date]
    if len({x['url'] for x in latest})!=1:raise ValueError('Ambiguous latest BOC board announcement')
    return latest[0],candidates
